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
        menu.get_by_id.return_value = item
        templates = TemplateService(str(Path(__file__).resolve().parents[1] / "front_py/templates"))
        cart = CartService()
        app.include_router(MenuRouter(menu, templates, cart).router)
        app.include_router(CartRouter(cart, menu, templates).router)
        app.include_router(TableRouter(templates).router)
        self.payment = AsyncMock()
        self.payment.get_methods.return_value = [{"id": "cash", "name": "เงินสด"}]
        self.payment.process.side_effect = lambda method, amount, items: {
            "method": method, "method_name": "เงินสด", "amount": amount,
            "message": "ทดสอบ", "qr_image": None,
        }
        app.include_router(PaymentRouter(self.payment, cart, menu, templates).router)
        self.app = app
        self.client = TestClient(app)

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

    def test_checkout_payment_and_finish_keep_the_correct_table(self):
        self.client.post("/cart/add/1")
        self.client.post("/cart/add/1?table=1")
        self.client.post("/cart/update/1?table=1", data={"quantity": 2})
        self.client.post("/cart/add/1?table=2")
        cart = PageLinks(self.client.get("/cart?table=1").text)
        checkout_url = next(url for url in cart.links if url.startswith("/checkout"))
        self.assertEqual(checkout_url, "/checkout?table=1")
        checkout = self.client.get(checkout_url)
        self.assertIn("100.00 บาท", checkout.text)
        checkout_links = PageLinks(checkout.text)
        self.assertIn("/cart?table=1", checkout_links.links)
        self.client.get("/?table=2")  # Another tab must not redirect table 1's payment.
        result = self.client.post(checkout_links.forms[0], data={"method": "cash"})
        self.assertIn("โต๊ะ 1", result.text)
        self.payment.process.assert_awaited_once_with(
            "cash", 100.0, [{"id": 1, "name": "ข้าวผัด", "price": 50, "qty": 2}],
        )
        finish = self.client.post(PageLinks(result.text).forms[0])
        self.assertEqual(finish.url.params["table"], "1")
        self.assertIn("ยังไม่มีสินค้าในตะกร้า", finish.text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=2").text)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart").text)

    def test_checkout_retry_preserves_table_on_payment_failure(self):
        self.client.post("/cart/add/1?table=10")
        self.payment.process.side_effect = httpx.ConnectError("test failure")
        response = self.client.post("/checkout/pay?table=10", data={"method": "cash"})
        self.assertIn("ติดต่อเซิร์ฟเวอร์ชำระเงินไม่ได้", response.text)
        self.assertIn("/checkout?table=10", PageLinks(response.text).links)
        self.assertIn("ยอดรวมทั้งหมด: 50", self.client.get("/cart?table=10").text)

    def test_empty_checkout_redirect_and_invalid_table_validation(self):
        self.client.post("/cart/add/1?table=2")
        for path in ("/checkout", "/checkout?table=1"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], path.replace("/checkout", "/cart"))
        response = self.client.post("/checkout/pay?table=1", data={"method": "cash"}, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/cart?table=1")
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

    def test_qr_count_can_be_changed_and_links_select_each_table(self):
        self.client.cookies.set("admin_token", "logged_in")
        for count in (1, 10):
            response = self.client.get("/admin/tables", params={"base_url": "http://testserver", "table_count": count})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text.count("<svg"), count)
            self.assertIn(f"พิมพ์ QR ทั้ง {count} โต๊ะ", response.text)
            for table in range(1, count + 1):
                self.assertIn(f'http://testserver/?table={table}', response.text)
                self.assertIn(f"โต๊ะ {table}", self.client.get(f"/?table={table}").text)

    def test_invalid_qr_counts_are_rejected(self):
        self.client.cookies.set("admin_token", "logged_in")
        for value in (0, -1, 101, "abc", "2.5"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get("/admin/tables", params={"table_count": value}).status_code, 422)

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

        # คนแรกขอจ่าย 1 จาน (50.-) + แชร์ของกลาง 20.- = รวม 70.-
        response = self.client.post("/checkout/pay?table=5", data={
            "method": "cash",
            "split_mode": "split",
            "selected_items": json.dumps({"1": 1}),
            "shared_amount": "20.0",
            "shared_note": "ค่าน้ำหาร 2 คน",
        })
        self.assertEqual(response.status_code, 200)
        # ตรวจสอบว่าแสดงยอดที่ชำระรอบนี้ 70.00 บาท
        self.assertIn("70.00", response.text)
        # ตรวจสอบว่าเหลือยอดค้างชำระของโต๊ะ 100.00 บาท
        self.assertIn("100.00", response.text)
        self.assertIn("/checkout?table=5", response.text)

        # ตรวจสอบว่าในตะกร้าของโต๊ะ 5 ถูกหักเหลือ 2 จาน ยอดรวม 100 บาท
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

        # ไปหน้าเช็คบิลเพื่อจ่ายเงินเมื่อทานเสร็จ ยอดต้องรวมทั้ง 2 รอบ = 150.00 บาท
        checkout = self.client.get("/checkout?table=7")
        self.assertIn("150.00", checkout.text)


if __name__ == "__main__":
    unittest.main()
