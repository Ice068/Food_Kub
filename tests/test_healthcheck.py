"""Readiness and diagnostics without credentials or a live backend."""
import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "front_py"))

from app.routers.menu_router import MenuRouter
from app.services.cart_service import CartService
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService


class HealthcheckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with patch.dict(os.environ, {"FOOD_KUB_SESSION_SECRET": "isolated-healthcheck-test-secret"}):
            from main import Application

            self.application = Application()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.application.get_app()), base_url="http://frontend.test"
        )
        self.addAsyncCleanup(self.client.aclose)

    def backend_response(self, response):
        return patch(
            "app.services.menu_service.backend_client",
            side_effect=lambda: httpx.AsyncClient(transport=httpx.MockTransport(response)),
        )

    async def test_get_and_head_require_a_usable_catalog(self):
        calls = []

        def backend(request):
            calls.append(request.url.path)
            return httpx.Response(200, json=[{
                "id": 1, "name": "Pad Thai", "price": 85,
                "image": "pad_thai.jpg", "category": "Main dishes",
            }])

        with self.backend_response(backend):
            response = await self.client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            head = await self.client.head("/healthz")
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head.content, b"")
        self.assertEqual(calls, ["/api/menu", "/api/menu"])

    async def test_empty_catalog_is_healthy(self):
        with self.backend_response(lambda request: httpx.Response(200, json=[])):
            self.assertEqual((await self.client.get("/healthz")).status_code, 200)

    async def test_http_failures_are_unavailable_without_upstream_details(self):
        secret = "never-expose-this-upstream-secret"
        failures = [
            httpx.ConnectError(secret),
            httpx.ReadTimeout(secret),
            httpx.HTTPStatusError(
                secret, request=httpx.Request("GET", f"http://private.test/?key={secret}"),
                response=httpx.Response(500, text=secret),
            ),
        ]
        for failure in failures:
            with self.subTest(error=type(failure).__name__):
                with patch.object(self.application.menu_service, "get_all", AsyncMock(side_effect=failure)):
                    response = await self.client.get("/healthz")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "unavailable"})
                self.assertNotIn(secret, response.text)
                self.assertNotIn("private.test", response.text)

    async def test_invalid_upstream_json_and_models_are_unavailable(self):
        responses = [
            httpx.Response(200, text="invalid-json-private-data"),
            httpx.Response(200, json=None),
            httpx.Response(200, json={"error": "private-data"}),
            httpx.Response(200, json=[{"id": 1}]),
        ]
        for upstream in responses:
            with self.subTest(body=upstream.text):
                with self.backend_response(lambda request: upstream):
                    response = await self.client.get("/healthz")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "unavailable"})

    async def test_slow_probe_is_cancelled_after_three_seconds(self):
        cancelled = asyncio.Event()

        async def slow_catalog():
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()

        started = time.monotonic()
        with patch.object(self.application.menu_service, "get_all", side_effect=slow_catalog):
            response = await self.client.get("/healthz")
        elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 503)
        self.assertTrue(cancelled.is_set())
        self.assertGreaterEqual(elapsed, 2.8)
        self.assertLess(elapsed, 5)

    async def test_catalog_diagnostics_log_only_error_class_and_status(self):
        secret = "private-key-material-never-log"
        service = MenuService()
        router = MenuRouter(service, TemplateService("unused"), CartService())
        failure = httpx.HTTPStatusError(
            secret, request=httpx.Request("GET", f"http://private.test/?key={secret}"),
            response=httpx.Response(502, text=secret),
        )
        with patch.object(service, "get_all", AsyncMock(side_effect=failure)):
            with self.assertLogs("app.routers.menu_router", level="WARNING") as logs:
                items, error = await router._catalog()
        self.assertEqual(items, [])
        self.assertTrue(error)
        self.assertIn("HTTPStatusError", logs.output[0])
        self.assertIn("502", logs.output[0])
        self.assertNotIn(secret, " ".join(logs.output))
        self.assertNotIn("private.test", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
