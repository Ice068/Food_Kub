from starlette.requests import Request


class CartService:
    """Store each customer's carts and active kitchen orders in their session, scoped by the request's table."""

    SESSION_KEY = "cart"
    ORDER_KEY = "orders"

    def _session_key(self, request: Request) -> str:
        table_id = getattr(request.state, "table_id", None)
        return f"cart_table_{table_id}" if table_id is not None else self.SESSION_KEY

    def _order_key(self, request: Request) -> str:
        table_id = getattr(request.state, "table_id", None)
        return f"order_table_{table_id}" if table_id is not None else self.ORDER_KEY

    def get_cart(self, request: Request) -> dict:
        """คืนค่า cart ที่กำลังเลือกสั่ง เป็น dict {item_id(str): quantity(int)}"""
        return request.session.get(self._session_key(request), {})

    def get_active_orders(self, request: Request) -> dict:
        """คืนค่ารายการอาหารที่ส่งเข้าครัวไปแล้วของโต๊ะนี้ {item_id(str): quantity(int)}"""
        return request.session.get(self._order_key(request), {})

    def send_cart_to_kitchen(self, request: Request) -> dict:
        """ส่งอาหารจากตะกร้าเข้าครัว (สะสมในบิลโต๊ะ) แล้วเคลียร์ตะกร้าสำหรับสั่งรอบใหม่"""
        cart = self.get_cart(request)
        if not cart:
            return {}
        orders = self.get_active_orders(request)
        for item_id, qty in cart.items():
            orders[item_id] = orders.get(item_id, 0) + qty
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

        request.session[self._order_key(request)] = orders
        request.session[self._session_key(request)] = cart

    def clear(self, request: Request):
        """ล้างเฉพาะตะกร้าที่กำลังเลือกสั่ง"""
        request.session[self._session_key(request)] = {}

    def clear_all(self, request: Request):
        """ล้างทั้งตะกร้าและบิลโต๊ะเมื่อชำระเงินเสร็จสิ้น"""
        request.session[self._session_key(request)] = {}
        request.session[self._order_key(request)] = {}

    def total_count(self, request: Request) -> int:
        return sum(self.get_cart(request).values())
