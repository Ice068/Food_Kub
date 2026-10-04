import asyncio
import hashlib
import json
import logging
import secrets
import time
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.core.table_context import set_table_context, table_query
from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.payment_service import PaymentService
from app.services.stats_service import StatsService, build_lines
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("ยอดเงินไม่ถูกต้อง")

    if (
        not amount.is_finite()
        or amount < 0
        or amount > Decimal("1000000")
    ):
        raise ValueError("ยอดเงินไม่ถูกต้อง")

    if amount != amount.quantize(CENT):
        raise ValueError("ยอดเงินต้องมีทศนิยมไม่เกิน 2 ตำแหน่ง")

    return amount.quantize(CENT)


class PaymentRouter:
    """ไม่หักบิลเมื่อผลชำระยังเป็น pending หรือไม่ทราบแน่ชัด"""

    def __init__(
        self,
        payment_service: PaymentService,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService,
        stats_service: StatsService,
    ):
        self.payment_service = payment_service
        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service
        self.stats_service = stats_service

        self.router = APIRouter(
            prefix="/checkout",
            dependencies=[Depends(set_table_context)],
        )

        # เก็บในหน่วยความจำของ process นี้เท่านั้น
        self._attempts = {}
        self._locks = {}
        self._pending = {}

        self.router.add_api_route(
            "",
            self.show_checkout,
            methods=["GET"],
        )
        self.router.add_api_route(
            "/pay",
            self.process_payment,
            methods=["POST"],
        )

    def _scope(self, request):
        owner = request.session.get("payment_owner")

        if not owner:
            owner = secrets.token_urlsafe(32)
            request.session["payment_owner"] = owner

        table = getattr(request.state, "table_id", None)

        scope = (
            f"table:{table}"
            if table is not None
            else f"session:{owner}"
        )

        return owner, scope

    def _render(self, request, context, status=200):
        response = self.template_service.render(
            request,
            "payment_result.html",
            context,
        )
        response.status_code = status
        response.headers["Cache-Control"] = "no-store"
        return response

    def _error(self, request, message, status=400):
        return self._render(
            request,
            {
                "title": "ผลการชำระเงิน",
                "error": message,
            },
            status,
        )

    @staticmethod
    def _fingerprint(items, total, shared_paid, shared_ids):
        payload = [
            sorted(items, key=lambda item: item["id"]),
            str(total),
            str(shared_paid),
            sorted(shared_ids),
        ]

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode()

        return hashlib.sha256(encoded).hexdigest()

    async def show_checkout(self, request: Request):
        owner, scope = self._scope(request)

        # มีรายการที่ยังไม่ทราบผล ให้แสดงรายการเดิม
        if scope in self._pending:
            return self._render(request, self._pending[scope])

        try:
            items, total, shared_ids, shared_paid = (
                await self._bill(request)
            )
        except ValueError as exc:
            return self._error(request, str(exc))
        except httpx.HTTPError:
            return self._error(
                request,
                "ตรวจสอบบิลไม่ได้ กรุณาลองใหม่",
                503,
            )

        if not items or total <= 0:
            return RedirectResponse(
                f"/cart{table_query(request)}",
                status_code=303,
            )

        now = time.monotonic()

        # ลบเฉพาะโทเค็นที่หมดอายุและยังไม่เคยส่งชำระ
        self._attempts = {
            key: value
            for key, value in self._attempts.items()
            if value.get("context") or value["expires"] > now
        }

        if len(self._attempts) >= 2000:
            return self._error(
                request,
                "ระบบชำระเงินเต็ม กรุณาติดต่อพนักงาน",
                503,
            )

        token = secrets.token_urlsafe(32)

        self._attempts[token] = {
            "owner": owner,
            "scope": scope,
            "expires": now + 900,
            "fingerprint": self._fingerprint(
                items,
                total,
                shared_paid,
                shared_ids,
            ),
            "context": None,
        }

        methods = await self.payment_service.get_methods()

        response = self.template_service.render(
            request,
            "checkout.html",
            {
                "title": "ชำระเงิน",
                "items": items,
                "total": float(total),
                "methods": methods,
                "cart_count": self.cart_service.total_count(request),
                "shared_paid": float(shared_paid),
                "shared_item_ids": sorted(shared_ids),
                "payment_token": token,
            },
        )

        response.headers["Cache-Control"] = "no-store"
        return response

    async def process_payment(
        self,
        request: Request,
        method: str = Form(...),
        split_mode: str = Form("full"),
        selected_items: str = Form("{}"),
        shared_amount: str = Form("0"),
        shared_note: str = Form(""),
        shared_item_ids: str = Form("[]"),
        payment_token: str = Form(""),
    ):
        owner, scope = self._scope(request)
        attempt = self._attempts.get(payment_token)

        if (
            not attempt
            or attempt["owner"] != owner
            or attempt["scope"] != scope
        ):
            return self._error(
                request,
                "คำขอไม่ถูกต้อง กรุณาเปิดหน้าชำระเงินใหม่",
                403,
            )

        # ป้องกันคำขอชำระพร้อมกันของโต๊ะเดียวกัน
        async with self._locks.setdefault(scope, asyncio.Lock()):
            # ส่งคำขอเดิมซ้ำ ให้คืนผลเดิม
            if attempt["context"] is not None:
                return self._render(request, attempt["context"])

            if attempt["expires"] <= time.monotonic():
                return self._error(
                    request,
                    "หน้าชำระเงินหมดอายุ กรุณาเปิดใหม่",
                    409,
                )

            if scope in self._pending:
                return self._render(request, self._pending[scope])

            try:
                if (
                    method not in {"cash", "qr_bank"}
                    or split_mode not in {"full", "split"}
                ):
                    raise ValueError(
                        "วิธีชำระเงินหรือรูปแบบบิลไม่ถูกต้อง"
                    )

                items, total, server_shared_ids, shared_paid = (
                    await self._bill(request)
                )

                if not items or total <= 0:
                    raise ValueError("ไม่มีรายการค้างชำระ")

                fingerprint = self._fingerprint(
                    items,
                    total,
                    shared_paid,
                    server_shared_ids,
                )

                if attempt["fingerprint"] != fingerprint:
                    return self._error(
                        request,
                        "บิลเปลี่ยนแล้ว กรุณาเปิดหน้าชำระเงินใหม่",
                        409,
                    )

                selected, submitted_shared_ids = self._parse_selection(
                    selected_items,
                    shared_item_ids,
                )

                shared = money(shared_amount)
                deducted = {}
                pay_items = []
                is_split = split_mode == "split"

                if is_split:
                    lookup = {item["id"]: item for item in items}

                    # รายการของกลางต้องตรงกับที่เซิร์ฟเวอร์กำหนด
                    if (
                        shared > 0
                        and set(submitted_shared_ids) != server_shared_ids
                    ):
                        raise ValueError(
                            "รายการของกลางไม่ตรงกับบิล "
                            "กรุณาเปิดหน้าชำระเงินใหม่"
                        )

                    for item_id, qty in selected.items():
                        item = lookup.get(item_id)

                        if not item or qty > item["qty"]:
                            raise ValueError(
                                "จำนวนอาหารเกินรายการค้างชำระ"
                            )

                        if item_id in server_shared_ids:
                            raise ValueError(
                                "รายการของกลางต้องชำระผ่านช่อง"
                                "ส่วนแบ่งของกลาง"
                            )

                        deducted[str(item_id)] = qty

                        pay_items.append({
                            "id": item["id"],
                            "name": item["name"],
                            "price": item["price"],
                            "qty": qty,
                        })

                    shared_cost = sum(
                        (
                            money(item["price"]) * item["qty"]
                            for item in items
                            if item["id"] in server_shared_ids
                        ),
                        Decimal(0),
                    )

                    unpaid_shared = max(
                        Decimal(0),
                        shared_cost - shared_paid,
                    )

                    if shared > unpaid_shared:
                        raise ValueError(
                            "ยอดส่วนแบ่งของกลางเกินยอดคงเหลือ"
                        )

                    if shared > 0:
                        pay_items.append({
                            "id": 9999,
                            "name": "ส่วนแบ่งของกลาง",
                            "price": float(shared),
                            "qty": 1,
                        })

                    amount = sum(
                        (
                            money(item["price"]) * item["qty"]
                            for item in pay_items
                        ),
                        Decimal(0),
                    )

                    if amount <= 0 or amount > total:
                        raise ValueError(
                            "กรุณาเลือกรายการที่ต้องการจ่าย "
                            "และตรวจสอบยอดเงิน"
                        )

                else:
                    pay_items = [
                        {
                            "id": item["id"],
                            "name": item["name"],
                            "price": item["price"],
                            "qty": item["qty"],
                        }
                        for item in items
                        if item["id"] not in server_shared_ids
                    ]

                    personal = sum(
                        (
                            money(item["price"]) * item["qty"]
                            for item in pay_items
                        ),
                        Decimal(0),
                    )

                    unpaid_shared = total - personal

                    if unpaid_shared > 0:
                        pay_items.append({
                            "id": 9999,
                            "name": "ยอดของกลางคงเหลือ",
                            "price": float(unpaid_shared),
                            "qty": 1,
                        })

                    amount = total

            except ValueError as exc:
                return self._error(request, str(exc))
            except httpx.HTTPError:
                return self._error(
                    request,
                    "ตรวจสอบบิลไม่ได้ กรุณาลองใหม่",
                    503,
                )

            context = {
                "title": "ผลการชำระเงิน",
                "total": float(amount),
                "is_split": is_split,
                "pay_items": pay_items,
                "remaining_total": float(total),
                "is_fully_paid": False,
                "payment_confirmed": False,
            }

            # ใช้โทเค็นนี้แล้วก่อนติดต่อ Backend
            attempt["context"] = context

            try:
                result = await self.payment_service.process(
                    method,
                    float(amount),
                    pay_items,
                )
            except (httpx.HTTPError, ValueError, TypeError):
                context["error"] = (
                    "ยังตรวจสอบผลรายการไม่ได้ "
                    "กรุณาติดต่อพนักงานก่อนจ่ายซ้ำ"
                )
                self._pending[scope] = context
                return self._render(request, context, 503)

            if not isinstance(result, dict):
                context["error"] = (
                    "ผลตอบกลับไม่ถูกต้อง "
                    "กรุณาติดต่อพนักงานก่อนจ่ายซ้ำ"
                )
                self._pending[scope] = context
                return self._render(request, context, 502)

            context["result"] = result

            try:
                valid = (
                    result.get("method") == method
                    and money(result.get("amount")) == amount
                )
            except ValueError:
                valid = False

            if not valid:
                context["error"] = (
                    "ยอดเงินหรือวิธีจ่ายจาก Backend ไม่ตรงกัน "
                    "กรุณาติดต่อพนักงาน"
                )
                self._pending[scope] = context
                return self._render(request, context, 502)

            # pending ยังไม่ใช่หลักฐานว่าชำระสำเร็จ
            if result.get("status") == "pending":
                self._pending[scope] = context
                return self._render(request, context)

            payment_id = result.get("payment_id")

            if (
                result.get("status") != "success"
                or not isinstance(payment_id, str)
                or not payment_id
            ):
                context["error"] = (
                    "ยังไม่มีหลักฐานยืนยันการชำระเงินจาก Backend "
                    "กรุณาติดต่อพนักงาน"
                )
                self._pending[scope] = context
                return self._render(request, context, 502)

            # ตรวจว่ามีคนเพิ่มอาหารระหว่างรอ Backend หรือไม่
            try:
                current_items, current_total, current_ids, current_paid = (
                    await self._bill(request)
                )

                same_bill = (
                    attempt["fingerprint"]
                    == self._fingerprint(
                        current_items,
                        current_total,
                        current_paid,
                        current_ids,
                    )
                )

                current_quantities = {
                    str(item["id"]): item["qty"]
                    for item in current_items
                }

                same_bill = (
                    same_bill
                    and current_quantities
                    == dict(self.cart_service.get_bill_items(request))
                )

            except (ValueError, httpx.HTTPError):
                same_bill = False

            if not same_bill:
                context["error"] = (
                    "Backend ยืนยันรับเงินแล้ว "
                    "แต่บิลเปลี่ยนระหว่างทำรายการ "
                    "กรุณาให้พนักงานตรวจสอบ ห้ามจ่ายซ้ำ"
                )
                self._pending[scope] = context
                return self._render(request, context, 409)

            # หักรายการเฉพาะเมื่อ Backend ยืนยันสำเร็จ
            if is_split:
                self.cart_service.deduct_items(request, deducted)

                if shared > 0:
                    self.cart_service.record_shared_payment(
                        request,
                        float(shared),
                        sorted(server_shared_ids),
                    )
                    self.cart_service.settle_fully_paid_shared_items(
                        request,
                        items,
                    )

                remaining = total - amount
                closed = remaining == 0

                if closed:
                    self.cart_service.clear_all(request)

            else:
                remaining = Decimal(0)
                closed = True
                self.cart_service.clear_all(request)

            context.update({
                "payment_confirmed": True,
                "remaining_total": float(remaining),
                "is_fully_paid": closed,
            })

            # ปัญหาของสถิติไม่ควรทำให้ลูกค้าต้องจ่ายเงินซ้ำ
            try:
                table = getattr(request.state, "table_id", None)

                written = await self.stats_service.record_transaction(
                    table,
                    method,
                    float(amount),
                    pay_items,
                    closed,
                )

                live = (
                    []
                    if closed
                    else await build_lines(
                        self.menu_service,
                        dict(
                            self.cart_service.get_active_orders(request)
                        ),
                    )
                )

                synced = (
                    await self.stats_service.sync_live_order(table, live)
                    if table is not None
                    else True
                )

                if not written or not synced:
                    logger.error(
                        "Confirmed payment %s requires stats reconciliation",
                        payment_id,
                    )

            except httpx.HTTPError:
                logger.exception(
                    "Confirmed payment requires stats reconciliation"
                )

            return self._render(request, context)

    @staticmethod
    def _parse_selection(selected_text, shared_text):
        if len(selected_text) > 16000 or len(shared_text) > 4000:
            raise ValueError("ข้อมูลรายการยาวเกินกำหนด")

        try:
            raw = json.loads(selected_text)
            ids = json.loads(shared_text)
        except (ValueError, TypeError):
            raise ValueError("ข้อมูลรายการอาหารไม่ถูกต้อง")

        if not isinstance(raw, dict) or not isinstance(ids, list):
            raise ValueError("รูปแบบรายการอาหารไม่ถูกต้อง")

        selected = {}

        for key, qty in raw.items():
            if (
                not key.isascii()
                or not key.isdecimal()
                or str(int(key)) != key
            ):
                raise ValueError("รหัสอาหารไม่ถูกต้อง")

            if type(qty) is not int or qty < 0 or qty > 1000:
                raise ValueError(
                    "จำนวนอาหารต้องเป็นจำนวนเต็มระหว่าง 0 ถึง 1000"
                )

            if qty:
                selected[int(key)] = qty

        if (
            any(type(item_id) is not int or item_id <= 0 for item_id in ids)
            or len(ids) != len(set(ids))
        ):
            raise ValueError("รายการของกลางไม่ถูกต้อง")

        return selected, ids

    async def _bill(self, request):
        quantities = dict(self.cart_service.get_bill_items(request))
        items = []

        for item_id, qty in quantities.items():
            if type(qty) is not int or qty <= 0 or qty > 1000:
                raise ValueError("จำนวนอาหารในบิลไม่ถูกต้อง")

            menu = await self.menu_service.get_by_id(int(item_id))

            if not menu:
                raise ValueError(
                    "มีอาหารที่ตรวจสอบราคาไม่ได้ "
                    "กรุณาติดต่อพนักงาน"
                )

            price = money(menu.price)

            items.append({
                "id": menu.id,
                "name": menu.name,
                "price": float(price),
                "qty": qty,
                "category": (
                    getattr(menu, "category", "ทั่วไป") or "ทั่วไป"
                ),
                "image_url": getattr(menu, "image_url", ""),
            })

        shared_ids = set(
            self.cart_service.get_shared_item_ids(request)
        )

        if not shared_ids:
            shared_ids = {
                item["id"]
                for item in items
                if (
                    "เครื่องดื่ม" in item["category"]
                    or any(
                        word in item["name"]
                        for word in ("น้ำ", "ชา", "โซดา", "น้ำแข็ง")
                    )
                )
            }

        shared_ids &= {item["id"] for item in items}

        paid = money(self.cart_service.get_shared_paid(request))

        shared_cost = sum(
            (
                money(item["price"]) * item["qty"]
                for item in items
                if item["id"] in shared_ids
            ),
            Decimal(0),
        )

        if paid > shared_cost:
            raise ValueError(
                "ยอดของกลางไม่สอดคล้องกัน กรุณาติดต่อพนักงาน"
            )

        gross = sum(
            (
                money(item["price"]) * item["qty"]
                for item in items
            ),
            Decimal(0),
        )

        total = money(gross - paid)
        return items, total, shared_ids, paid