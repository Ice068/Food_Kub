import asyncio
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
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


class BillChangedError(ValueError):
    """บิลเปลี่ยนหลังเปิดหน้าชำระเงิน ใช้คืน HTTP 409"""


@dataclass
class PaymentInput:
    method: str
    split_mode: str
    selected_items: str
    shared_amount: str
    shared_item_ids: str


@dataclass
class SplitSelection:
    selected: dict[int, int]
    shared_ids: set[int]
    shared: Decimal


@dataclass
class PaymentPlan:
    method: str
    items: list[dict]
    total: Decimal
    shared_ids: set[int]
    shared: Decimal
    is_split: bool
    deducted: dict[str, int]
    pay_items: list[dict]
    amount: Decimal


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

        await self.stats_service.sync_live_order(
            getattr(request.state, "table_id", None),
            items,
            status="waiting_payment",
        )

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

        if not self._owns_attempt(attempt, owner, scope):
            return self._error(
                request,
                "คำขอไม่ถูกต้อง กรุณาเปิดหน้าชำระเงินใหม่",
                403,
            )

        # คง lock ครอบคลุมตั้งแต่ตรวจโทเค็นจนบันทึกผล
        async with self._locks.setdefault(scope, asyncio.Lock()):
            early_response = self._attempt_response(request, scope, attempt)
            if early_response is not None:
                return early_response

            submitted = PaymentInput(
                method=method,
                split_mode=split_mode,
                selected_items=selected_items,
                shared_amount=shared_amount,
                shared_item_ids=shared_item_ids,
            )
            return await self._execute_payment(request, scope, attempt, submitted)

    @staticmethod
    def _owns_attempt(attempt, owner, scope) -> bool:
        if not attempt:
            return False
        return attempt["owner"] == owner and attempt["scope"] == scope

    def _attempt_response(self, request, scope, attempt):
        # คำขอเดิมที่ส่งซ้ำ คืนผลเดิมโดยไม่เรียกชำระอีก
        if attempt["context"] is not None:
            return self._render(request, attempt["context"])
        if attempt["expires"] <= time.monotonic():
            return self._error(request, "หน้าชำระเงินหมดอายุ กรุณาเปิดใหม่", 409)
        if scope in self._pending:
            return self._render(request, self._pending[scope])
        return None

    async def _execute_payment(self, request, scope, attempt, submitted):
        try:
            plan = await self._prepare_payment(request, attempt, submitted)
        except BillChangedError as exc:
            return self._error(request, str(exc), 409)
        except ValueError as exc:
            return self._error(request, str(exc))
        except httpx.HTTPError:
            return self._error(request, "ตรวจสอบบิลไม่ได้ กรุณาลองใหม่", 503)

        context = self._payment_context(plan)
        # ใช้โทเค็นนี้ก่อนติดต่อ Backend ป้องกันการส่งชำระซ้ำ
        attempt["context"] = context

        response = await self._request_payment(request, scope, plan, context)
        if response is not None:
            return response

        if not await self._same_bill(request, attempt):
            return self._pending_response(
                request, scope, context,
                "Backend ยืนยันรับเงินแล้ว แต่บิลเปลี่ยนระหว่างทำรายการ "
                "กรุณาให้พนักงานตรวจสอบ ห้ามจ่ายซ้ำ",
                409,
            )

        remaining, closed = self._apply_payment(request, plan)
        context.update({
            "payment_confirmed": True,
            "remaining_total": float(remaining),
            "is_fully_paid": closed,
        })
        await self._record_payment(request, plan, context["result"]["payment_id"], closed)
        return self._render(request, context)

    async def _prepare_payment(self, request, attempt, submitted):
        if (
            submitted.method not in {"cash", "qr_bank"}
            or submitted.split_mode not in {"full", "split"}
        ):
            raise ValueError("วิธีชำระเงินหรือรูปแบบบิลไม่ถูกต้อง")

        items, total, shared_ids, shared_paid = await self._bill(request)
        if not items or total <= 0:
            raise ValueError("ไม่มีรายการค้างชำระ")
        fingerprint = self._fingerprint(items, total, shared_paid, shared_ids)
        if attempt["fingerprint"] != fingerprint:
            raise BillChangedError("บิลเปลี่ยนแล้ว กรุณาเปิดหน้าชำระเงินใหม่")

        selected, submitted_ids = self._parse_selection(
            submitted.selected_items, submitted.shared_item_ids,
        )
        shared = money(submitted.shared_amount)
        is_split = submitted.split_mode == "split"

        if is_split:
            deducted, pay_items, amount = self._split_payment(
                items, total, shared_ids, shared_paid,
                SplitSelection(selected, set(submitted_ids), shared),
            )
        else:
            deducted = {}
            pay_items = self._full_payment_items(items, total, shared_ids)
            amount = total

        return PaymentPlan(
            method=submitted.method, items=items, total=total,
            shared_ids=shared_ids, shared=shared, is_split=is_split,
            deducted=deducted, pay_items=pay_items, amount=amount,
        )

    @staticmethod
    def _payment_line(item, qty):
        return {
            "id": item["id"], "name": item["name"],
            "price": item["price"], "qty": qty,
        }

    @staticmethod
    def _items_amount(items):
        return sum(
            (money(item["price"]) * item["qty"] for item in items),
            Decimal(0),
        )

    @staticmethod
    def _shared_line(name, amount):
        return {"id": 9999, "name": name, "price": float(amount), "qty": 1}

    def _selected_payment_items(self, items, selected, shared_ids):
        lookup = {item["id"]: item for item in items}
        deducted = {}
        pay_items = []
        for item_id, qty in selected.items():
            item = lookup.get(item_id)
            if not item or qty > item["qty"]:
                raise ValueError("จำนวนอาหารเกินรายการค้างชำระ")
            if item_id in shared_ids:
                raise ValueError("รายการของกลางต้องชำระผ่านช่องส่วนแบ่งของกลาง")
            deducted[str(item_id)] = qty
            pay_items.append(self._payment_line(item, qty))
        return deducted, pay_items

    def _split_payment(self, items, total, shared_ids, shared_paid, selection):
        if selection.shared > 0 and selection.shared_ids != shared_ids:
            raise ValueError("รายการของกลางไม่ตรงกับบิล กรุณาเปิดหน้าชำระเงินใหม่")

        deducted, pay_items = self._selected_payment_items(
            items, selection.selected, shared_ids,
        )
        shared_items = [item for item in items if item["id"] in shared_ids]
        unpaid_shared = max(Decimal(0), self._items_amount(shared_items) - shared_paid)
        if selection.shared > unpaid_shared:
            raise ValueError("ยอดส่วนแบ่งของกลางเกินยอดคงเหลือ")
        if selection.shared > 0:
            pay_items.append(self._shared_line("ส่วนแบ่งของกลาง", selection.shared))
        amount = self._items_amount(pay_items)
        if amount <= 0 or amount > total:
            raise ValueError("กรุณาเลือกรายการที่ต้องการจ่าย และตรวจสอบยอดเงิน")
        return deducted, pay_items, amount

    def _full_payment_items(self, items, total, shared_ids):
        pay_items = [
            self._payment_line(item, item["qty"])
            for item in items if item["id"] not in shared_ids
        ]
        unpaid_shared = total - self._items_amount(pay_items)
        if unpaid_shared > 0:
            pay_items.append(self._shared_line("ยอดของกลางคงเหลือ", unpaid_shared))
        return pay_items

    @staticmethod
    def _payment_context(plan):
        return {
            "title": "ผลการชำระเงิน", "total": float(plan.amount),
            "is_split": plan.is_split, "pay_items": plan.pay_items,
            "remaining_total": float(plan.total), "is_fully_paid": False,
            "payment_confirmed": False,
        }

    def _pending_response(self, request, scope, context, message=None, status=200):
        if message is not None:
            context["error"] = message
        self._pending[scope] = context
        return self._render(request, context, status)

    @staticmethod
    def _valid_payment_result(result, plan):
        try:
            return result.get("method") == plan.method and money(result.get("amount")) == plan.amount
        except ValueError:
            return False

    @staticmethod
    def _is_confirmed(result):
        payment_id = result.get("payment_id")
        return (
            result.get("status") == "success"
            and isinstance(payment_id, str)
            and bool(payment_id)
        )

    async def _request_payment(self, request, scope, plan, context):
        try:
            result = await self.payment_service.process(
                plan.method, float(plan.amount), plan.pay_items,
            )
        except (httpx.HTTPError, ValueError, TypeError):
            return self._pending_response(
                request, scope, context,
                "ยังตรวจสอบผลรายการไม่ได้ กรุณาติดต่อพนักงานก่อนจ่ายซ้ำ", 503,
            )

        if not isinstance(result, dict):
            return self._pending_response(
                request, scope, context,
                "ผลตอบกลับไม่ถูกต้อง กรุณาติดต่อพนักงานก่อนจ่ายซ้ำ", 502,
            )
        context["result"] = result
        if not self._valid_payment_result(result, plan):
            return self._pending_response(
                request, scope, context,
                "ยอดเงินหรือวิธีจ่ายจาก Backend ไม่ตรงกัน กรุณาติดต่อพนักงาน", 502,
            )
        if result.get("status") == "pending":
            return self._pending_response(request, scope, context)
        if not self._is_confirmed(result):
            return self._pending_response(
                request, scope, context,
                "ยังไม่มีหลักฐานยืนยันการชำระเงินจาก Backend กรุณาติดต่อพนักงาน", 502,
            )
        return None

    async def _same_bill(self, request, attempt):
        try:
            items, total, shared_ids, shared_paid = await self._bill(request)
            same_fingerprint = attempt["fingerprint"] == self._fingerprint(
                items, total, shared_paid, shared_ids,
            )
            quantities = {str(item["id"]): item["qty"] for item in items}
            return same_fingerprint and quantities == dict(self.cart_service.get_bill_items(request))
        except (ValueError, httpx.HTTPError):
            return False

    def _apply_payment(self, request, plan):
        if not plan.is_split:
            self.cart_service.clear_all(request)
            return Decimal(0), True

        self.cart_service.deduct_items(request, plan.deducted)
        if plan.shared > 0:
            self.cart_service.record_shared_payment(
                request, float(plan.shared), sorted(plan.shared_ids),
            )
            self.cart_service.settle_fully_paid_shared_items(request, plan.items)
        remaining = plan.total - plan.amount
        closed = remaining == 0
        if closed:
            self.cart_service.clear_all(request)
        return remaining, closed

    async def _sync_payment_table(self, request, plan, closed):
        table = getattr(request.state, "table_id", None)
        if table is None:
            return True
        if closed:
            # ส่งอาหารจริงรวมของกลาง เก็บโต๊ะไว้จนพนักงานกด Reset
            return await self.stats_service.mark_table_paid(table, plan.items)
        live = await build_lines(
            self.menu_service, dict(self.cart_service.get_active_orders(request)),
        )
        return await self.stats_service.sync_live_order(table, live, status="waiting_payment")

    async def _record_payment(self, request, plan, payment_id, closed):
        # ปัญหาสถิติต้องไม่ทำให้ลูกค้าจ่ายเงินซ้ำ
        try:
            written = await self.stats_service.record_transaction(
                getattr(request.state, "table_id", None), plan.method,
                float(plan.amount), plan.pay_items, closed,
            )
            synced = await self._sync_payment_table(request, plan, closed)
            if not written or not synced:
                logger.error("Confirmed payment %s requires stats reconciliation", payment_id)
        except httpx.HTTPError:
            logger.exception("Confirmed payment requires stats reconciliation")


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
            PaymentRouter._validate_selected_item(key, qty)
            if qty:
                selected[int(key)] = qty

        if (
            any(type(item_id) is not int or item_id <= 0 for item_id in ids)
            or len(ids) != len(set(ids))
        ):
            raise ValueError("รายการของกลางไม่ถูกต้อง")

        return selected, ids

    @staticmethod
    def _validate_selected_item(key, qty):
        if (
            not key.isascii()
            or not key.isdecimal()
            or str(int(key)) != key
        ):
            raise ValueError("รหัสอาหารไม่ถูกต้อง")
        if type(qty) is not int or qty < 0 or qty > 1000:
            raise ValueError("จำนวนอาหารต้องเป็นจำนวนเต็มระหว่าง 0 ถึง 1000")

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
