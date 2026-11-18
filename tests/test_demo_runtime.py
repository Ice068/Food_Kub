"""Behavioral coverage for the isolated local runtime and cart contract."""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "front_py"))
from app.core.config import settings
from app.core.admin_auth import create_admin_token, valid_admin_token
from app.services.demo_service import demo_request
from app.services.cart_service import CartService


class DemoRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for name, value in (("DEMO_MODE", True), ("DEMO_DB", Path(self.directory.name) / "demo.sqlite3")):
            change = patch.object(settings, name, value)
            change.start()
            self.addCleanup(change.stop)
        self.api = httpx.Client(transport=httpx.MockTransport(demo_request), base_url="http://demo.test")
        self.addCleanup(self.api.close)

    def test_seed_uses_existing_images_and_survives_reopening(self):
        menu = self.api.get("/api/menu").json()
        self.assertEqual(len(menu), 12)
        for item in menu:
            self.assertTrue((ROOT / "front_py/static/images" / item["image"]).is_file())
        created = self.api.post("/api/admin/add", json={"name": "ข้าวไข่เจียว", "price": 55,
            "category": "จานเดียว", "image": "menu-placeholder.svg"}).json()["item"]
        with httpx.Client(transport=httpx.MockTransport(demo_request), base_url="http://demo.test") as second:
            self.assertEqual(second.get(f"/api/menu/{created['id']}").json()["name"], "ข้าวไข่เจียว")

    def test_demo_payment_is_explicit_and_cannot_create_bank_qr(self):
        methods = self.api.get("/api/payment/methods").json()
        self.assertEqual([m["id"] for m in methods], ["cash"])
        result = self.api.post("/api/payment/process", json={"method": "cash", "amount": 85, "items": []}).json()
        self.assertTrue(result["demo"])
        self.assertTrue(result["payment_id"].startswith("demo-"))
        self.assertNotIn("qr_image", result)
        self.assertEqual(self.api.post("/api/payment/process", json={"method": "qr_bank", "amount": 85}).status_code, 400)

    def test_table_versions_block_stale_updates_and_unpaid_reset(self):
        items = [{"id": 1, "name": "ผัดไทย", "price": 85, "qty": 1}]
        opened = self.api.put("/api/stats/live-orders/1", json={"items": items, "status": "dining"}).json()["table"]
        self.assertEqual(self.api.put("/api/stats/live-orders/1", json={"items": items,
            "expected_opened_at": "stale"}).status_code, 409)
        self.assertEqual(self.api.post("/api/stats/live-orders/1/reset", json={"opened_at": opened["opened_at"]}).status_code, 409)
        payload = {"opened_at": opened["opened_at"], "items": items, "expected_total": 85, "method": "cash"}
        confirmed = self.api.post("/api/stats/live-orders/1/confirm-payment", json=payload)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["table"]["total"], 0)
        self.assertEqual(confirmed.json()["table"]["items"], [])
        self.assertEqual(confirmed.json()["table"]["paid_amount"], 85)
        self.assertEqual(self.api.post("/api/stats/live-orders/1/confirm-payment", json=payload).status_code, 409)
        dashboard = self.api.get("/api/stats/dashboard").json()
        self.assertEqual(dashboard["revenue"]["today"], 85)
        self.assertEqual(dashboard["bills"]["today"], 1)
        self.assertEqual(dashboard["tables"]["live"][0]["total"], 0)
        self.assertEqual(self.api.post("/api/stats/live-orders/1/reset", json={"opened_at": opened["opened_at"]}).status_code, 200)

    def test_menu_cannot_be_deleted_while_in_unpaid_bill(self):
        self.api.put("/api/stats/live-orders/1", json={"items": [{"id": 1, "name": "ผัดไทย", "price": 85, "qty": 1}]})
        self.assertEqual(self.api.post("/api/admin/delete/1").status_code, 409)

    def test_admin_tokens_are_signed_and_tampering_is_rejected(self):
        token = create_admin_token()
        self.assertTrue(valid_admin_token(token))
        self.assertFalse(valid_admin_token("logged_in"))
        self.assertFalse(valid_admin_token(token + "broken"))

    def test_frontend_cart_json_validation_and_persistence(self):
        from main import app
        with TestClient(app) as client:
            headers = {"Accept": "application/json"}
            added = client.post("/cart/add/1", headers=headers)
            self.assertEqual(added.status_code, 200)
            self.assertEqual(added.json()["cart_count"], 1)
            self.assertEqual(added.json()["total"], 85)
            self.assertIn("image_url", added.json()["items"][0])
            self.assertEqual(client.get("/cart/state").json()["cart"], {"1": 1})
            self.assertEqual(client.post("/cart/add/99999", headers=headers).status_code, 404)
            self.assertEqual(client.post("/cart/update/1", data={"quantity": 100}, headers=headers).status_code, 422)
            self.api.post("/api/stats/availability/1", json={"available": False})
            self.assertEqual(client.post("/cart/add/1", headers=headers).status_code, 409)
            self.assertEqual(client.post("/cart/remove/1", headers=headers).json()["cart_count"], 0)

    def test_frontend_admin_requires_real_signed_login_and_supports_edit(self):
        from main import app
        with TestClient(app) as client:
            client.cookies.set("admin_token", "logged_in")
            self.assertEqual(client.get("/admin/", follow_redirects=False).status_code, 303)
            client.cookies.clear()
            login = client.post("/admin/login", data={"username": "admin", "password": "demo-food-kub"}, follow_redirects=False)
            self.assertEqual(login.status_code, 303)
            edited = client.post("/admin/edit/1", data={"name": "ผัดไทยกุ้งใหญ่", "price": 99, "category": "จานเดียว"}, follow_redirects=False)
            self.assertEqual(edited.status_code, 303)
            self.assertEqual(self.api.get("/api/menu/1").json()["price"], 99)

    def test_real_payment_strategies_do_not_claim_confirmed_payment(self):
        # Load strategy modules without importing Firestore or using credentials.
        base_path = ROOT / "blackend_py/app/services/payments"
        modules = {}
        for name in ("base", "cash_strategy", "qr_bank_strategy"):
            module_name = f"app.services.payments.{name}"
            spec = importlib.util.spec_from_file_location(module_name, base_path / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            modules[module_name] = module
            with patch.dict(sys.modules, modules):
                spec.loader.exec_module(module)
        cash = modules["app.services.payments.cash_strategy"].CashPaymentStrategy().process(85, [])
        qr = modules["app.services.payments.qr_bank_strategy"].QrBankPaymentStrategy("0812345678").process(85, [])
        self.assertEqual(cash["status"], "pending")
        self.assertEqual(qr["status"], "pending")
        self.assertTrue(qr["qr_image"])

    def test_table_checkout_split_across_customers_and_paid_persistence(self):
        from main import app
        def token(page):
            self.assertEqual(page.status_code, 200)
            match = re.search(r'name="payment_token"\s+value="([^"]+)"', page.text)
            self.assertIsNotNone(match)
            return match[1]
        with TestClient(app) as first, TestClient(app) as second:
            first.post("/cart/add/1?table=1", headers={"Accept": "application/json"})
            first.post("/cart/update/1?table=1", data={"quantity": 2}, headers={"Accept": "application/json"})
            first.post("/cart/add/11?table=1", headers={"Accept": "application/json"})
            checkout = first.get("/checkout?table=1")
            result = first.post("/checkout/pay?table=1", data={"payment_token": token(checkout),
                "method": "cash", "split_mode": "split", "selected_items": json.dumps({"1": 1}),
                "shared_item_ids": "[11]", "shared_amount": "20"})
            self.assertEqual(result.status_code, 200)
            live = self.api.get("/api/stats/live-orders/1").json()["table"]
            self.assertEqual(live["total"], 105)
            self.assertFalse(live["paid"])
            result = second.post("/checkout/pay?table=1", data={"payment_token": token(second.get("/checkout?table=1")),
                "method": "cash", "split_mode": "split", "selected_items": json.dumps({"1": 1}),
                "shared_item_ids": "[11]", "shared_amount": "20"})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(first.get("/checkout/status?table=1").json()["payment_confirmed"])
            self.assertEqual(first.get("/cart/state?table=1").json()["bill_count"], 0)
            dashboard = self.api.get("/api/stats/dashboard").json()
            self.assertEqual(dashboard["revenue"]["today"], 210)
            self.assertEqual(dashboard["bills"]["today"], 1)
            self.assertEqual(dashboard["tables"]["live"][0]["total"], 0)
            self.assertEqual(dashboard["tables"]["live"][0]["paid_amount"], 210)

    def test_table_count_blocks_unknown_tables_but_preserves_existing_bills(self):
        from main import app
        self.api.put("/api/stats/live-orders/10", json={"items": [{"id": 1, "name": "ผัดไทย", "price": 85, "qty": 1}]})
        self.api.put("/api/table-settings", json={"table_count": 5})
        with TestClient(app) as client:
            headers = {"Accept": "application/json"}
            self.assertEqual(client.get("/cart/state?table=6", headers=headers).status_code, 404)
            self.assertEqual(client.get("/cart/state?table=10", headers=headers).status_code, 200)

    def test_production_guest_must_scan_before_ordering_or_paying(self):
        from main import app
        with TestClient(app) as client:
            headers = {"Accept": "application/json"}
            client.post("/cart/add/1", headers=headers)
            with patch.object(settings, "DEMO_MODE", False):
                self.assertEqual(client.post("/cart/send-to-kitchen", headers=headers).status_code, 409)
                self.assertEqual(client.get("/checkout", headers=headers).status_code, 409)
            self.assertEqual(client.get("/cart/state").json()["cart_count"], 1)

    def test_cart_budget_rejects_overflow_without_losing_existing_items(self):
        from fastapi import HTTPException
        from starlette.requests import Request
        request = Request({"type": "http", "session": {}})
        cart = CartService()
        with self.assertRaises(HTTPException):
            for item_id in range(1, 1000):
                before = dict(cart.get_cart(request))
                cart.add_item(request, item_id)
        self.assertEqual(cart.get_cart(request), before)
        self.assertLessEqual(len(json.dumps(request.session).encode()), CartService.MAX_SESSION_BYTES)


if __name__ == "__main__":
    unittest.main()
