"""Run with python -B -m unittest discover -s tests -v."""
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "front_py"))
from app.models.menu_item import MenuItem
from app.routers.cart_router import CartRouter
from app.routers.menu_router import MenuRouter
from app.routers.table_router import TableRouter
from app.routers.payment_router import PaymentRouter
from app.services.cart_service import CartService
from app.services.template_service import TemplateService


class FakeStatsBackend:
    """Stands in for StatsService and the Backend live-orders endpoint (in memory)."""

    backend_url = "http://backend.test"

    def __init__(self):
        self.live = {}
        self.orders = []
        self.transactions = []
        self.table_count = 5
        self._tick = 0

    def _stamp(self):
        self._tick += 1
        return f"2026-01-01T00:00:{self._tick:02d}+00:00"

    async def sync_live_order(
        self, table, items, status="dining", shared_paid=0,
        expected_opened_at=None, expected_updated_at=None,
    ):
        if not items:
            self.live.pop(table, None)
            return True
        previous = self.live.get(table, {})
        self.live[table] = {
            "table": table,
            "items": [dict(item) for item in items],
            "status": status,
            "shared_paid": shared_paid,
            "paid": False,
            "opened_at": previous.get("opened_at") or self._stamp(),
            "updated_at": self._stamp(),
        }
        return True

    async def record_order(self, table, items):
        self.orders.append((table, items))
        return True

    async def record_transaction(self, *args, **kwargs):
        self.transactions.append((args, kwargs))
        return True

    async def mark_table_paid(self, table, items):
        self.live.pop(table, None)
        return True

    def client_class(self):
        backend = self

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url, **kwargs):
                if url.rstrip("/").endswith("/api/table-settings"):
                    return FakeResponse({"table_count": backend.table_count})
                table = int(url.rstrip("/").rsplit("/", 1)[1])
                return FakeResponse({"table": backend.live.get(table)})

            async def put(self, url, json=None, **kwargs):
                backend.table_count = json["table_count"]
                return FakeResponse({"table_count": backend.table_count})

        return FakeClient


class PageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.forms = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "a":
            self.links.append(attributes.get("href", ""))
        elif tag == "form":
            self.forms.append(attributes.get("action", ""))


class TableQrTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-only")
        menu = AsyncMock()
        item = MenuItem(1, "ข้าวผัด", 50, "rice.jpg", "อาหาร")
        menu.get_all.return_value = [item]
        menu.get_categories.return_value = ["อาหาร"]
        menu.get_by_category.return_value = [item]
        drink = MenuItem(2, "น้ำเปล่า", 20, "water.jpg", "เครื่องดื่ม")
        menu.get_by_id.side_effect = lambda item_id: {1: item, 2: drink}.get(item_id)
        templates = TemplateService(str(Path(__file__).resolve().parents[1] / "front_py/templates"))
        cart = CartService()
        self.stats = FakeStatsBackend()
        live_patch = patch(
            "app.core.table_context.httpx.AsyncClient",
            self.stats.client_class(),
        )
        live_patch.start()
        self.addCleanup(live_patch.stop)
        app.include_router(MenuRouter(menu, templates, cart).router)
        app.include_router(CartRouter(cart, menu, templates, self.stats).router)
        app.include_router(TableRouter(templates).router)
        self.payment = AsyncMock()
        self.payment.get_methods.return_value = [{"id": "cash", "name": "เงินสด"}]
        self.payment.process.side_effect = lambda method, amount, items: {
            "status": "success", "payment_id": "test-payment-1",
            "method": method, "method_name": "เงินสด", "amount": amount,
            "message": "ทดสอบ", "qr_image": None,
        }
        app.include_router(PaymentRouter(self.payment, cart, menu, templates, self.stats).router)
        self.app = app
        self.client = TestClient(app)

    def open_checkout(self, table):
        """Open /checkout like a customer and return (response, payment_token)."""
        import re
        page = self.client.get(f"/checkout?table={table}")
        match = re.search(r'name="payment_token"\s+value="([^"]+)"', page.text)
        return page, (match.group(1) if match else "")

    def pay(self, table, **data):
        """Open checkout for the table, then submit a payment with its token."""
        _, token = self.open_checkout(table)
        data.setdefault("method", "cash")
        data["payment_token"] = token
        return self.client.post(f"/checkout/pay?table={table}", data=data)

    def test_table_is_retained_in_navigation_and_forms(self):
        for table in (1, 2, 3, 4, 5, 10, 100):
            with self.subTest(table=table):
                response = self.client.get(f"/?table={table}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.url.params["table"], str(table))
                page = PageLinks(response.text)
                for url in page.links:
                    linked = self.client.get(url)
                    self.assertEqual(linked.status_code, 200)
                    self.assertIn(f"โต๊ะ {table}", linked.text)
                added = self.client.post(page.forms[0])
                self.assertEqual(added.url.params["table"], str(table))
                self.assertIn("ยอดรวมทั้งหมด: 50", added.text)

    def test_all_tables_and_general_menu_have_separate_carts(self):
        # The same cookie jar represents multiple tabs in the same browser.
        self.client.post("/cart/add/1")
        for table in range(1, 11):
            self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get(f"/cart?table={table}").text)
            self.client.post(f"/cart/add/1?table={table}")
            self.client.post(f"/cart/update/1?table={table}", data={"quantity": table + 1})
        # Opening another table must not change any previously opened tab's cart.
        for table in range(1, 11):
            self.assertIn(f"ยอดรวมทั้งหมด: {50 * (table + 1)}", self.client.get(f"/cart?table={table}").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart").text)

    def test_stale_tab_forms_change_only_their_own_table(self):
        self.client.post("/cart/add/1?table=1")
        first_tab = PageLinks(self.client.get("/cart?table=1").text)
        self.client.get("/?table=2")
        self.client.post("/cart/add/1?table=2")
        response = self.client.post(first_tab.forms[0], data={"quantity": 4})
        self.assertEqual(response.url.params["table"], "1")
        self.assertIn("ยอดรวมทั้งหมด: 200", response.text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)
        self.client.post(first_tab.forms[2])  # Remove from the older table-1 tab.
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get("/cart?table=1").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)
        self.client.post("/cart/add/1?table=1")
        self.client.post(first_tab.forms[3])  # Clear only table 1.
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get("/cart?table=1").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)
        self.client.post("/cart/clear")
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)

    def test_rescan_same_table_keeps_cart(self):
        self.client.get("/?table=3")
        self.client.post("/cart/add/1?table=3")
        self.client.get("/?table=3")
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=3").text)

    def test_invalid_table_cannot_read_or_change_cart(self):
        self.client.post("/cart/add/1?table=4")
        for value in ("0", "101", "-1", "abc", "1.5", ""):
            with self.subTest(value=value):
                for path in ("/", "/cart", "/category/อาหาร"):
                    self.assertEqual(self.client.get(f"{path}?table={value}").status_code, 422)
                for path in ("/cart/add/1", "/cart/remove/1", "/cart/clear", "/cart/update/1"):
                    response = self.client.post(f"{path}?table={value}", data={"quantity": 99})
                    self.assertEqual(response.status_code, 422)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=4").text)
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get("/cart").text)

    def test_customers_do_not_share_carts(self):
        other = TestClient(self.app)
        self.client.get("/?table=1")
        self.client.post("/cart/add/1?table=1")
        other.get("/?table=1")
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", other.get("/cart?table=1").text)

    def test_no_scan_shows_prompt_and_legacy_cart_stays_separate(self):
        self.assertIn("ยังไม่ได้ระบุโต๊ะ", self.client.get("/").text)
        self.client.post("/cart/add/1")
        self.client.get("/?table=1")
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get("/cart?table=1").text)
        self.assertIn("ยังไม่ได้ระบุโต๊ะ", self.client.get("/").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart").text)

    def test_existing_session_carts_survive_and_old_active_table_is_ignored(self):
        import base64
        import json
        from itsdangerous import TimestampSigner
        legacy = {"table_id": 1, "cart": {"1": 2}, "cart_table_1": {"1": 3}}
        cookie = TimestampSigner("test-only").sign(base64.b64encode(json.dumps(legacy).encode())).decode()
        self.client.cookies.set("session", cookie, domain="testserver.local", path="/")
        self.assertIn("ยังไม่ได้ระบุโต๊ะ", self.client.get("/").text)
        self.assertIn("ยอดรวมทั้งหมด: 100", self.client.get("/cart").text)
        self.assertIn("ยอดรวมทั้งหมด: 150", self.client.get("/cart?table=1").text)

    def test_qr_page_requires_admin(self):
        response = self.client.get("/admin/tables", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin/login")

    def test_checkout_payment_keeps_the_correct_table(self):
        self.client.post("/cart/add/1")
        self.client.post("/cart/add/1?table=1")
        self.client.post("/cart/update/1?table=1", data={"quantity": 2})
        self.client.post("/cart/add/1?table=2")
        cart = PageLinks(self.client.get("/cart?table=1").text)
        checkout_url = next(url for url in cart.links if url.startswith("/checkout"))
        self.assertEqual(checkout_url, "/checkout?table=1")
        checkout, token = self.open_checkout(1)
        self.assertIn("100.00 บาท", checkout.text)
        self.assertTrue(token)
        self.assertIn("/cart?table=1", PageLinks(checkout.text).links)
        self.client.get("/?table=2")  # Another tab must not redirect table 1's payment.
        result = self.client.post(
            "/checkout/pay?table=1",
            data={"method": "cash", "payment_token": token},
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("โต๊ะ 1", result.text)
        self.payment.process.assert_awaited_once()
        method, amount, _items = self.payment.process.await_args.args
        self.assertEqual((method, amount), ("cash", 100.0))
        # Fully paid: table 1 bill is closed, other tables and the general cart are untouched.
        self.assertNotIn(1, self.stats.live)
        self.assertEqual(len(self.stats.transactions), 1)
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", self.client.get("/cart?table=1").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart").text)

    def test_payment_without_token_is_rejected(self):
        self.client.post("/cart/add/1?table=10")
        response = self.client.post("/checkout/pay?table=10", data={"method": "cash"})
        self.assertEqual(response.status_code, 403)
        self.payment.process.assert_not_awaited()

    def test_payment_failure_keeps_bill_and_table(self):
        self.client.post("/cart/add/1?table=10")
        self.payment.process.side_effect = httpx.ConnectError("test failure")
        response = self.pay(10)
        self.assertEqual(response.status_code, 503)
        self.assertIn("กรุณาติดต่อพนักงานก่อนจ่ายซ้ำ", response.text)
        self.assertIn("/checkout?table=10", PageLinks(response.text).links)
        # The bill must not be closed or recorded as paid.
        self.assertIn(10, self.stats.live)
        self.assertEqual(self.stats.transactions, [])
        self.assertIn("50.00", self.client.get("/cart?table=10").text)

    def test_empty_checkout_redirect_and_invalid_table_validation(self):
        self.client.post("/cart/add/1?table=2")
        for path in ("/checkout", "/checkout?table=1"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], path.replace("/checkout", "/cart"))
        self.assertEqual(self.client.get("/checkout?table=101").status_code, 422)
        self.assertEqual(self.client.post("/checkout/pay?table=101", data={"method": "cash"}).status_code, 422)
        self.payment.process.assert_not_awaited()

    def test_qr_payloads_match_printed_links(self):
        import qrcode
        self.client.cookies.set("admin_token", "logged_in")
        with patch("app.routers.table_router.qrcode.make", wraps=qrcode.make) as make:
            response = self.client.get("/admin/tables", params={"base_url": "https://menu.example.com/"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count("<svg"), 5)
        self.assertEqual([call.args[0] for call in make.call_args_list], [
            f"https://menu.example.com/?table={i}" for i in range(1, 6)
        ])
        for table in range(1, 6):
            self.assertIn(f'https://menu.example.com/?table={table}', response.text)

    def test_invalid_base_urls_do_not_generate_qr(self):
        self.client.cookies.set("admin_token", "logged_in")
        for url in ("javascript:alert(1)", "https://site.test/?table=8", "https://site.test/#x", "http://user:pass@site.test", "http://site.test:bad", ""):
            with self.subTest(url=url):
                response = self.client.get("/admin/tables", params={"base_url": url})
                self.assertIn('role="alert"', response.text)
                self.assertNotIn("<svg", response.text)

    def test_qr_count_is_saved_to_backend_and_links_select_each_table(self):
        self.client.cookies.set("admin_token", "logged_in")
        for count in (1, 10):
            response = self.client.post(
                "/admin/tables",
                data={"base_url": "http://testserver", "table_count": count},
            )  # follows the 303 redirect back to the QR page
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.stats.table_count, count)
            self.assertEqual(response.text.count("<svg"), count)
            self.assertIn(f"พิมพ์ QR ทั้ง {count} โต๊ะ", response.text)
            for table in range(1, count + 1):
                self.assertIn(f'http://testserver/?table={table}', response.text)
                self.assertIn(f"โต๊ะ {table}", self.client.get(f"/?table={table}").text)

    def test_invalid_qr_counts_are_rejected(self):
        self.client.cookies.set("admin_token", "logged_in")
        for value in (0, -1, 101, "abc", "2.5"):
            with self.subTest(value=value):
                response = self.client.post(
                    "/admin/tables",
                    data={"base_url": "http://testserver", "table_count": value},
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.stats.table_count, 5)

    def test_invalid_base_url_is_not_saved(self):
        self.client.cookies.set("admin_token", "logged_in")
        response = self.client.post(
            "/admin/tables",
            data={"base_url": "javascript:alert(1)", "table_count": 3},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stats.table_count, 5)

    def test_localhost_warning_and_public_url_setting(self):
        self.client.cookies.set("admin_token", "logged_in")
        response = self.client.get("/admin/tables", params={"base_url": "http://localhost:8001"})
        self.assertIn("URL นี้ใช้ได้เฉพาะเครื่องเซิร์ฟเวอร์", response.text)
        with patch.dict("os.environ", {"PUBLIC_BASE_URL": "https://food.example.com"}):
            response = self.client.get("/admin/tables")
        self.assertIn("https://food.example.com/?table=5", response.text)

    def test_split_bill_itemized_and_shared_pool(self):
        import json
        # โต๊ะ 5 สั่ง 3 จาน (จานละ 50 = 150)
        self.client.post("/cart/add/1?table=5")
        self.client.post("/cart/update/1?table=5", data={"quantity": 3})
        self.client.post("/cart/add/2?table=5")  # น้ำเปล่า 20.- เป็นของกลาง (170.- ทั้งบิล)

        # คนแรกขอจ่าย 1 จาน (50.-) + แชร์ของกลาง 20.- = รวม 70.-
        response = self.pay(5, **{
            "split_mode": "split",
            "selected_items": json.dumps({"1": 1}),
            "shared_amount": "20.0",
            "shared_note": "ค่าน้ำหาร 2 คน",
            "shared_item_ids": json.dumps([2]),
        })
        self.assertEqual(response.status_code, 200)
        # ตรวจสอบว่าแสดงยอดที่ชำระรอบนี้ 70.00 บาท
        self.assertIn("70.00", response.text)
        # ตรวจสอบว่าเหลือยอดค้างชำระของโต๊ะ 100.00 บาท
        self.assertIn("100.00", response.text)
        self.assertIn("/checkout?table=5", response.text)

        # โต๊ะ 5 ยังเปิดบิลอยู่ และในตะกร้าถูกหักเหลือ 2 จาน ยอดรวม 100 บาท
        self.assertIn(5, self.stats.live)
        cart_resp = self.client.get("/cart?table=5")
        self.assertIn("100", cart_resp.text)

    def test_send_to_kitchen_multiple_rounds_and_pay_later(self):
        # สั่งรอบที่ 1: ข้าวผัด 1 จาน (50.-) -> ส่งเข้าครัว
        self.client.post("/cart/add/1?table=7")
        resp1 = self.client.post("/cart/send-to-kitchen?table=7", follow_redirects=True)
        self.assertIn("50.00", resp1.text)

        # สั่งรอบที่ 2: ข้าวผัดเพิ่มอีก 2 จาน (100.-) -> ส่งเข้าครัว
        self.client.post("/cart/add/1?table=7")
        self.client.post("/cart/update/1?table=7", data={"quantity": 2})
        resp2 = self.client.post("/cart/send-to-kitchen?table=7", follow_redirects=True)
        # ยอดสะสมในบิลโต๊ะต้องเป็น 3 จาน = 150.00 บาท
        self.assertIn("150.00", resp2.text)
        self.assertEqual(len(self.stats.orders), 2)

        # ไปหน้าเช็คบิลเพื่อจ่ายเงินเมื่อทานเสร็จ ยอดต้องรวมทั้ง 2 รอบ = 150.00 บาท
        checkout = self.client.get("/checkout?table=7")
        self.assertIn("150.00", checkout.text)

    def test_second_person_pays_remaining_shared_amount(self):
        import json
        # โต๊ะ 9 สั่ง 2 จาน (จานละ 50 = 100)
        self.client.post("/cart/add/1?table=9")
        self.client.post("/cart/update/1?table=9", data={"quantity": 2})
        self.client.post("/cart/add/2?table=9")  # น้ำเปล่า 20.- เป็นของกลาง

        # คนแรกขอจ่าย 1 จาน (50.-) + จ่ายส่วนแบ่งของกลางแค่ 10.- จาก 20.- (โดยส่ง shared_item_ids=[2])
        resp1 = self.pay(9, **{
            "split_mode": "split",
            "selected_items": json.dumps({"1": 1}),
            "shared_amount": "10.0",
            "shared_note": "แชร์ของกลาง",
            "shared_item_ids": json.dumps([2]),
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("60.00", resp1.text)

        # คนที่สองเปิดหน้า checkout ของโต๊ะ 9 ต้องเห็นว่ามียอดของกลางที่จ่ายไปแล้ว 10 บาท และยอดที่เหลือถูกหัก
        checkout_resp = self.client.get("/checkout?table=9")
        self.assertEqual(checkout_resp.status_code, 200)
        self.assertIn("หักส่วนของกลางที่เพื่อนร่วมโต๊ะชำระแล้ว", checkout_resp.text)
        self.assertIn("-10.00", checkout_resp.text)
        # ยอดคงเหลือที่ต้องจ่ายจริงของโต๊ะคือ 60.00 บาท (ข้าวผัด 50 + น้ำ 20 - ของกลางจ่ายแล้ว 10)
        self.assertIn("60.00", checkout_resp.text)


if __name__ == "__main__":
    unittest.main()
