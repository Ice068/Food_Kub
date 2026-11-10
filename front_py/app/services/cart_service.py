from starlette.requests import Request


class CartService:
    """Store each customer's carts and active kitchen orders in their session, scoped by the request's table."""

    SESSION_KEY = "cart"
    ORDER_KEY = "orders"
    SHARED_PAID_KEY = "shared_paid"
    SHARED_ITEMS_KEY = "shared_items"

    # In-memory table store shared across devices at the same table
    TABLE_STATE: dict[str, dict] = {}

    def _get_table_id(self, request: Request) -> str | None:
        table_id = getattr(request.state, "table_id", None)
        return str(table_id) if table_id is not None else None

    def _get_table_state(self, str_tid: str, request: Request) -> dict:
        if str_tid not in self.TABLE_STATE:
            sess_orders = dict(request.session.get(f"{self.ORDER_KEY}_table_{str_tid}", {}))
            sess_paid = float(request.session.get(f"{self.SHARED_PAID_KEY}_table_{str_tid}", 0.0))
            sess_items = set(request.session.get(f"{self.SHARED_ITEMS_KEY}_table_{str_tid}", []))
            self.TABLE_STATE[str_tid] = {
                "orders": sess_orders,
                "shared_paid": sess_paid,
                "shared_item_ids": sess_items,
            }
        return self.TABLE_STATE[str_tid]

    def _session_key(self, request: Request) -> str:
        tid = self._get_table_id(request)
        return f"cart_table_{tid}" if tid is not None else self.SESSION_KEY

    def _order_key(self, request: Request) -> str:
        tid = self._get_table_id(request)
        return f"order_table_{tid}" if tid is not None else self.ORDER_KEY

    def get_cart(self, request: Request) -> dict:
        """คืนค่า cart ที่กำลังเลือกสั่ง เป็น dict {item_id(str): quantity(int)}"""
        return request.session.get(self._session_key(request), {})

    def get_active_orders(self, request: Request) -> dict:
        """คืนค่ารายการอาหารที่ส่งเข้าครัวไปแล้วของโต๊ะนี้ {item_id(str): quantity(int)}"""
        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            return state["orders"]
        return request.session.get(self._order_key(request), {})

    def send_cart_to_kitchen(self, request: Request) -> dict:
        """ส่งอาหารจากตะกร้าเข้าครัว (สะสมในบิลโต๊ะ) แล้วเคลียร์ตะกร้าสำหรับสั่งรอบใหม่"""
        cart = self.get_cart(request)
        if not cart:
            return {}
        orders = self.get_active_orders(request)
        for item_id, qty in cart.items():
            orders[item_id] = orders.get(item_id, 0) + qty

        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            state["orders"] = orders
        request.session[self._order_key(request)] = orders
        self.clear(request)
        return orders

    def get_bill_items(self, request: Request) -> dict:
        """คืนค่ารายการอาหารทั้งหมดที่ต้องคิดเงิน (บิลในครัว + ของในตะกร้า)"""
        orders = dict(self.get_active_orders(request))
        cart = self.get_cart(request)
        for item_id, qty in cart.items():
            orders[item_id] = orders.get(item_id, 0) + qty
        return orders

    def bill_total_count(self, request: Request) -> int:
        return sum(self.get_bill_items(request).values())

    def add_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        key = str(item_id)
        cart[key] = cart.get(key, 0) + 1
        request.session[self._session_key(request)] = cart

    def update_quantity(self, request: Request, item_id: int, quantity: int):
        cart = self.get_cart(request)
        key = str(item_id)
        if quantity <= 0:
            cart.pop(key, None)
        else:
            cart[key] = quantity
        request.session[self._session_key(request)] = cart

    def remove_item(self, request: Request, item_id: int):
        cart = self.get_cart(request)
        cart.pop(str(item_id), None)
        request.session[self._session_key(request)] = cart

    def deduct_items(self, request: Request, items_to_deduct: dict):
        """หักจำนวนรายการที่ชำระเงินแล้วออกจากทั้งบิลในครัวและตะกร้า"""
        orders = self.get_active_orders(request)
        cart = self.get_cart(request)

        for item_id, qty in items_to_deduct.items():
            key = str(item_id)
            needed = int(qty)
            # ตัดจาก active_orders ที่ส่งเข้าครัวก่อน
            if key in orders:
                if orders[key] <= needed:
                    needed -= orders[key]
                    orders.pop(key, None)
                else:
                    orders[key] -= needed
                    needed = 0
            # ถ้ายังเหลือตัดจากตะกร้า
            if needed > 0 and key in cart:
                if cart[key] <= needed:
                    cart.pop(key, None)
                else:
                    cart[key] -= needed

        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            state["orders"] = orders
        request.session[self._order_key(request)] = orders
        request.session[self._session_key(request)] = cart

    def record_shared_payment(self, request: Request, amount: float, shared_item_ids: list[int] | None = None):
        """บันทึกยอดเงินที่ชำระให้กองกลาง (ค่าน้ำ/น้ำแข็ง/ของกลาง) สำหรับโต๊ะนี้"""
        clean_amt = max(0.0, float(amount or 0.0))
        if clean_amt <= 0:
            return

        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            state["shared_paid"] = round(state["shared_paid"] + clean_amt, 2)
            if shared_item_ids:
                state["shared_item_ids"].update(int(i) for i in shared_item_ids)
            request.session[f"{self.SHARED_PAID_KEY}_table_{tid}"] = state["shared_paid"]
            request.session[f"{self.SHARED_ITEMS_KEY}_table_{tid}"] = list(state["shared_item_ids"])
        else:
            curr = float(request.session.get(self.SHARED_PAID_KEY, 0.0))
            request.session[self.SHARED_PAID_KEY] = round(curr + clean_amt, 2)
            if shared_item_ids:
                existing = set(request.session.get(self.SHARED_ITEMS_KEY, []))
                existing.update(int(i) for i in shared_item_ids)
                request.session[self.SHARED_ITEMS_KEY] = list(existing)

    def get_shared_paid(self, request: Request) -> float:
        """ดึงยอดเงินกองกลางที่ถูกชำระไปแล้วของโต๊ะนี้"""
        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            return state["shared_paid"]
        return float(request.session.get(self.SHARED_PAID_KEY, 0.0))

    def get_shared_item_ids(self, request: Request) -> set[int]:
        """ดึงรายการ ID เมนูที่ถูกตั้งเป็นของกลางไว้ของโต๊ะนี้"""
        tid = self._get_table_id(request)
        if tid is not None:
            state = self._get_table_state(tid, request)
            return set(state["shared_item_ids"])
        return set(request.session.get(self.SHARED_ITEMS_KEY, []))

    def settle_fully_paid_shared_items(self, request: Request, items_info: list[dict] | None = None):
        """ถ้าของกลางถูกชำระจนครบตามราคารายการ ให้ตัดรายการของกลางที่ชำระครบแล้วออกจากบิล"""
        if not items_info:
            return

        shared_paid = self.get_shared_paid(request)
        if shared_paid <= 0:
            return

        shared_ids = self.get_shared_item_ids(request)
        if not shared_ids:
            return

        # คำนวณราคาของแต่ละเมนูกองกลางที่อยู่ในบิล
        deduct_dict = {}
        remaining_paid = shared_paid

        for item in items_info:
            i_id = item["id"]
            if i_id in shared_ids:
                item_price = float(item["price"])
                item_qty = int(item["qty"])
                total_item_cost = item_price * item_qty

                if remaining_paid >= total_item_cost:
                    # ชำระครบทั้งจำนวนของเมนูนี้
                    deduct_dict[str(i_id)] = item_qty
                    remaining_paid -= total_item_cost
                    shared_ids.remove(i_id)

        if deduct_dict:
            self.deduct_items(request, deduct_dict)
            tid = self._get_table_id(request)
            if tid is not None:
                state = self._get_table_state(tid, request)
                state["shared_paid"] = round(remaining_paid, 2)
                state["shared_item_ids"] = shared_ids
                request.session[f"{self.SHARED_PAID_KEY}_table_{tid}"] = state["shared_paid"]
                request.session[f"{self.SHARED_ITEMS_KEY}_table_{tid}"] = list(shared_ids)
            else:
                request.session[self.SHARED_PAID_KEY] = round(remaining_paid, 2)
                request.session[self.SHARED_ITEMS_KEY] = list(shared_ids)

    def clear(self, request: Request):
        """ล้างเฉพาะตะกร้าที่กำลังเลือกสั่ง"""
        request.session[self._session_key(request)] = {}

    def clear_all(self, request: Request):
        """ล้างทั้งตะกร้าและบิลโต๊ะเมื่อชำระเงินเสร็จสิ้นครบถ้วน"""
        tid = self._get_table_id(request)
        if tid is not None:
            if tid in self.TABLE_STATE:
                self.TABLE_STATE[tid] = {
                    "orders": {},
                    "shared_paid": 0.0,
                    "shared_item_ids": set(),
                }
            request.session.pop(f"{self.SHARED_PAID_KEY}_table_{tid}", None)
            request.session.pop(f"{self.SHARED_ITEMS_KEY}_table_{tid}", None)
            request.session.pop(self._order_key(request), None)

        request.session[self._session_key(request)] = {}
        request.session[self._order_key(request)] = {}
        request.session.pop(self.SHARED_PAID_KEY, None)
        request.session.pop(self.SHARED_ITEMS_KEY, None)

    def total_count(self, request: Request) -> int:
        return sum(self.get_cart(request).values())

