import json
import httpx
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse

from app.core.table_context import set_table_context, table_query

from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.payment_service import PaymentService
from app.services.template_service import TemplateService


class PaymentRouter:
    """รับ request หน้าชำระเงิน แล้วประสานงานระหว่างตะกร้ากับ PaymentService"""

    def __init__(
        self,
        payment_service: PaymentService,
        cart_service: CartService,
        menu_service: MenuService,
        template_service: TemplateService,
    ):
        self.router = APIRouter(prefix="/checkout", dependencies=[Depends(set_table_context)])

        self.payment_service = payment_service
        self.cart_service = cart_service
        self.menu_service = menu_service
        self.template_service = template_service

        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("", self.show_checkout, methods=["GET"])
        self.router.add_api_route("/pay", self.process_payment, methods=["POST"])

    async def show_checkout(self, request: Request):
        """หน้าเลือกวิธีจ่ายเงิน พร้อมสรุปรายการที่สั่งและตัวเลือกหารบิล/แยกจ่าย"""
        items, total = await self._build_order(request)

        # ตะกร้าว่าง ไม่มีอะไรให้จ่าย ส่งกลับไปหน้าตะกร้า
        if not items:
            return RedirectResponse(url=f"/cart{table_query(request)}", status_code=303)

        methods = await self.payment_service.get_methods()

        return self.template_service.render(
            request,
            "checkout.html",
            {
                "title": "ชำระเงิน",
                "items": items,
                "total": total,
                "methods": methods,
                "cart_count": self.cart_service.total_count(request),
                "shared_paid": self.cart_service.get_shared_paid(request),
                "shared_item_ids": list(self.cart_service.get_shared_item_ids(request)),
            },
        )

    async def process_payment(
        self,
        request: Request,
        method: str = Form(...),
        split_mode: str = Form("full"),
        selected_items: str = Form("{}"),
        shared_amount: float = Form(0.0),
        shared_note: str = Form(""),
        shared_item_ids: str = Form("[]"),
    ):
        """ส่งคำสั่งจ่ายเงินไปหลังบ้าน รองรับทั้งจ่ายเต็มบิลและแยกจ่ายรายคน (Split Bill)"""
        items, total = await self._build_order(request)

        if not items:
            return RedirectResponse(url=f"/cart{table_query(request)}", status_code=303)

        is_split = (split_mode == "split")
        pay_amount = total
        pay_items = items
        deducted_map = {}
        clean_shared = 0.0

        if is_split:
            try:
                selected_map = json.loads(selected_items) if selected_items else {}
            except Exception:
                selected_map = {}

            item_lookup = {item["id"]: item for item in items}
            custom_items = []
            personal_sum = 0.0

            for str_id, qty in selected_map.items():
                try:
                    i_id = int(str_id)
                    q = int(qty)
                except ValueError:
                    continue

                if i_id in item_lookup and q > 0:
                    src = item_lookup[i_id]
                    actual_q = min(q, src["qty"])
                    personal_sum += src["price"] * actual_q
                    custom_items.append({
                        "id": i_id,
                        "name": src["name"],
                        "price": src["price"],
                        "qty": actual_q,
                    })
                    deducted_map[str_id] = actual_q

            clean_shared = max(0.0, float(shared_amount or 0.0))
            if clean_shared > 0:
                note = shared_note.strip() or "ค่าน้ำ/ของกลาง"
                custom_items.append({
                    "id": 9999,
                    "name": f"ส่วนแบ่งของกลาง • {note}",
                    "price": round(clean_shared, 2),
                    "qty": 1,
                })

            calculated_total = round(personal_sum + clean_shared, 2)
            if calculated_total > 0 and custom_items:
                pay_amount = calculated_total
                pay_items = custom_items
            else:
                # ถ้าไม่ได้เลือกรายการใดเลย ให้จ่ายทั้งบิลตามปกติ
                is_split = False
                pay_amount = total
                pay_items = items

        # กรองเฉพาะฟิลด์มาตรฐานที่ backend payment API ต้องการ (id, name, price, qty)
        clean_pay_items = [
            {
                "id": it["id"],
                "name": it["name"],
                "price": it["price"],
                "qty": it["qty"]
            }
            for it in pay_items
        ]

        context = {
            "title": "ผลการชำระเงิน",
            "total": pay_amount,
            "cart_count": self.cart_service.total_count(request),
            "is_split": is_split,
            "pay_items": clean_pay_items,
        }

        try:
            context["result"] = await self.payment_service.process(method, pay_amount, clean_pay_items)
            if is_split:
                # 1. หักอาหารจานส่วนตัวที่เลือกชำระ
                if deducted_map:
                    self.cart_service.deduct_items(request, deducted_map)

                # 2. บันทึกยอดเงินกองกลางที่ชำระไปแล้ว
                if clean_shared > 0:
                    try:
                        passed_shared_ids = json.loads(shared_item_ids) if shared_item_ids else []
                    except Exception:
                        passed_shared_ids = []
                    self.cart_service.record_shared_payment(request, clean_shared, passed_shared_ids)

                # 3. ตัดรายการของกลางที่ชำระครบเต็มจำนวนแล้ว
                self.cart_service.settle_fully_paid_shared_items(request, items)

                remaining_items, remaining_total = await self._build_order(request)
                context["remaining_total"] = remaining_total
                context["is_fully_paid"] = (len(remaining_items) == 0 or remaining_total <= 0.01)
                if context["is_fully_paid"]:
                    self.cart_service.clear_all(request)
            else:
                self.cart_service.clear_all(request)
                context["remaining_total"] = 0.0
                context["is_fully_paid"] = True

        except httpx.HTTPStatusError:
            context["error"] = "ไม่สามารถทำรายการได้ กรุณาเลือกวิธีจ่ายเงินอีกครั้ง"
        except httpx.HTTPError:
            context["error"] = "ติดต่อเซิร์ฟเวอร์ชำระเงินไม่ได้ กรุณาลองใหม่"

        return self.template_service.render(request, "payment_result.html", context)

    # ---------- ตัวช่วยภายใน ----------

    async def _build_order(self, request: Request) -> tuple[list[dict], float]:
        """แปลงบิลของโต๊ะ (รวมที่สั่งเข้าครัวแล้วและของในตะกร้า) เป็นรายการสั่งซื้อ + ยอดรวมคงเหลือที่ต้องจ่ายจริง"""
        bill_items = self.cart_service.get_bill_items(request)

        items = []
        for item_id, qty in bill_items.items():
            menu_item = await self.menu_service.get_by_id(int(item_id))
            if menu_item:
                items.append({
                    "id": menu_item.id,
                    "name": menu_item.name,
                    "price": menu_item.price,
                    "category": getattr(menu_item, "category", "ทั่วไป"),
                    "image_url": getattr(menu_item, "image_url", ""),
                    "qty": qty,
                })

        shared_ids = set(self.cart_service.get_shared_item_ids(request))
        if not shared_ids:
            for item in items:
                cat = (item.get("category") or "").lower()
                nm = (item.get("name") or "").lower()
                if "เครื่องดื่ม" in cat or any(w in nm for w in ("น้ำ", "ชา", "โซดา", "น้ำแข็ง")):
                    shared_ids.add(item["id"])

        shared_items_cost = 0.0
        personal_items_cost = 0.0
        for item in items:
            if item["id"] in shared_ids:
                shared_items_cost += item["price"] * item["qty"]
            else:
                personal_items_cost += item["price"] * item["qty"]

        shared_paid = self.cart_service.get_shared_paid(request)
        unpaid_shared = max(0.0, round(shared_items_cost - shared_paid, 2))
        remaining_total = round(personal_items_cost + unpaid_shared, 2)

        return items, remaining_total


