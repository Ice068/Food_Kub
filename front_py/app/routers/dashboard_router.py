from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, StrictBool

from app.services.menu_service import MenuService
from app.services.stats_service import StatsService
from app.services.template_service import TemplateService

TH_TZ = timezone(timedelta(hours=7))

DAYS_TH = (
    "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."
)

MONTHS_TH = (
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.",
    "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.",
    "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
)

METHODS_TH = {
    "cash": "เงินสด",
    "qr_bank": "QR พร้อมเพย์",
}


def baht(value) -> str:
    value = float(value or 0)

    text = (
        f"{value:,.0f}"
        if value == int(value)
        else f"{value:,.2f}"
    )

    return "฿" + text


def _pct(value: float, maximum: float) -> int:
    if not maximum or value <= 0:
        return 0

    return max(3, round(value / maximum * 100))


def _trend(change_pct) -> dict:
    if change_pct is None:
        return {"kind": "none"}

    if change_pct == 0:
        return {"kind": "flat"}

    return {
        "kind": "up" if change_pct > 0 else "down",
        "value": abs(change_pct),
    }


class AvailabilityPayload(BaseModel):
    available: StrictBool


class DashboardRouter:
    """หน้า Dashboard และ JSON API สำหรับรีเฟรชด้วย JavaScript"""

    def __init__(
        self,
        stats_service: StatsService,
        menu_service: MenuService,
        template_service: TemplateService,
    ):
        self.router = APIRouter(prefix="/admin/dashboard")

        self.stats_service = stats_service
        self.menu_service = menu_service
        self.template_service = template_service

        self.template_service.templates.env.filters["baht"] = baht

        self.router.add_api_route(
            "",
            self.show_dashboard,
            methods=["GET"],
        )

        self.router.add_api_route(
            "/",
            self.show_dashboard,
            methods=["GET"],
            include_in_schema=False,
        )

        self.router.add_api_route(
            "/data",
            self.get_dashboard_data,
            methods=["GET"],
        )

        self.router.add_api_route(
            "/availability/{item_id}",
            self.set_availability,
            methods=["POST"],
        )

    @staticmethod
    def _is_admin(admin_token: str | None) -> bool:
        return admin_token == "logged_in"

    @staticmethod
    def _json(content: dict, status_code: int = 200):
        return JSONResponse(
            content=content,
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    # ---------- หน้า Dashboard ----------

    async def show_dashboard(
        self,
        request: Request,
        show_all: int = Query(0, alias="all"),
        admin_token: str | None = Cookie(None),
    ):
        if not self._is_admin(admin_token):
            return RedirectResponse(
                "/admin/login",
                status_code=303,
            )

        error = None
        data = None

        try:
            data = await self.stats_service.get_dashboard()
        except httpx.HTTPError:
            error = (
                "ติดต่อเซิร์ฟเวอร์หลังบ้านไม่ได้ "
                "กรุณาตรวจสอบว่า Backend พอร์ต 8000 เปิดอยู่"
            )

        try:
            menu = await self.menu_service.get_all()
        except httpx.HTTPError:
            menu = []

        context = self._build_view(data, menu)

        context.update({
            "title": "แดชบอร์ดภาพรวมร้าน",
            "error": error,
            "show_all": bool(show_all),
            "refresh_seconds": 10,
        })

        response = self.template_service.render(
            request,
            "dashboard.html",
            context,
        )

        response.headers["Cache-Control"] = "no-store"
        return response

    # ---------- JSON ที่หน้าเว็บดึงทุก 10 วินาที ----------

    async def get_dashboard_data(
        self,
        admin_token: str | None = Cookie(None),
    ):
        if not self._is_admin(admin_token):
            return self._json(
                {"error": "กรุณาเข้าสู่ระบบ Admin"},
                401,
            )

        try:
            data = await self.stats_service.get_dashboard()
            menu = await self.menu_service.get_all()

            data["menu"] = [
                {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "price": item.price,
                    "available": getattr(
                        item,
                        "available",
                        True,
                    ),
                }
                for item in menu
            ]

            return self._json(data)

        except httpx.HTTPError:
            return self._json(
                {
                    "error": (
                        "ติดต่อ Backend ไม่ได้ "
                        "กรุณาตรวจสอบพอร์ต 8000"
                    )
                },
                503,
            )

    # ---------- เปิด/ปิดขายเมนู รับ JSON ----------

    async def set_availability(
        self,
        item_id: int,
        payload: AvailabilityPayload,
        admin_token: str | None = Cookie(None),
    ):
        if not self._is_admin(admin_token):
            return self._json(
                {"error": "กรุณาเข้าสู่ระบบ Admin"},
                401,
            )

        try:
            updated = await self.stats_service.set_availability(
                item_id,
                payload.available,
            )

            if not updated:
                return self._json(
                    {"error": "ไม่พบเมนูนี้"},
                    404,
                )

            return self._json({
                "status": "success",
                "id": item_id,
                "available": payload.available,
            })

        except httpx.HTTPError:
            return self._json(
                {"error": "บันทึกสถานะเมนูไม่สำเร็จ"},
                503,
            )

    # ---------- ข้อมูลสำหรับเรนเดอร์หน้า ----------

    def _build_view(
        self,
        data: dict | None,
        menu: list,
    ) -> dict:
        now = datetime.now(TH_TZ)

        today_label = (
            f"{DAYS_TH[now.weekday()]} "
            f"{now.day} "
            f"{MONTHS_TH[now.month - 1]} "
            f"{now.year + 543}"
        )

        menu_rows = [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "available": getattr(item, "available", True),
            }
            for item in menu
        ]

        availability = {
            item["id"]: item["available"]
            for item in menu_rows
        }

        view = {
            "today_label": today_label,
            "updated_at": now.strftime("%H:%M:%S"),
            "menu": menu_rows,
            "has_data": data is not None,
        }

        if data is None:
            data = {
                "revenue": {
                    "today": 0,
                    "yesterday": 0,
                    "change_pct": None,
                },
                "bills": {
                    "today": 0,
                    "yesterday": 0,
                    "change_pct": None,
                },
                "tables": {
                    "active": 0,
                    "total": 0,
                    "live": [],
                },
                "top_dish": None,
                "top_dishes": [],
                "recent_transactions": [],
                "sales_trend": [],
                "sales_by_hour": [],
            }

        view["revenue"] = {
            **data["revenue"],
            "trend": _trend(data["revenue"]["change_pct"]),
        }

        view["bills"] = {
            **data["bills"],
            "trend": _trend(data["bills"]["change_pct"]),
        }

        view["top_dish"] = data["top_dish"]

        # โต๊ะทั้งหมดและรายการที่เปิดอยู่
        live = {
            table["table"]: table
            for table in data["tables"]["live"]
        }

        total = data["tables"]["total"]
        active = data["tables"]["active"]

        numbers = sorted(
            set(range(1, total + 1)) | set(live)
        )

        view["tables"] = {
            "active": active,
            "total": total,
            "free": max(0, total - active),
            "bar": (
                min(100, round(active / total * 100))
                if total
                else 0
            ),
            "tiles": [
                {
                    "number": number,
                    "live": live.get(number),
                    "shown": (
                        live[number]["items"][:4]
                        if number in live
                        else []
                    ),
                    "more": (
                        max(
                            0,
                            len(live[number]["items"]) - 4,
                        )
                        if number in live
                        else 0
                    ),
                }
                for number in numbers
            ],
        }

        # รายการเงินเข้าล่าสุด
        view["transactions"] = [
            {
                **transaction,
                "time": (
                    datetime.fromisoformat(
                        transaction["created_at"]
                    )
                    .astimezone(TH_TZ)
                    .strftime("%H:%M:%S")
                ),
                "method_name": METHODS_TH.get(
                    transaction["method"],
                    transaction["method"],
                ),
            }
            for transaction in data["recent_transactions"]
        ]

        # กราฟยอดขายรายวัน
        trend = data["sales_trend"]
        peak = max(
            (day["total"] for day in trend),
            default=0,
        )

        view["trend_bars"] = []

        for index, row in enumerate(trend):
            day = datetime.strptime(
                row["date"],
                "%Y-%m-%d",
            )

            view["trend_bars"].append({
                "label": f"{DAYS_TH[day.weekday()]} {day.day}",
                "total": row["total"],
                "pct": _pct(row["total"], peak),
                "is_today": index == len(trend) - 1,
            })

        # กราฟยอดขายรายชั่วโมง
        hours = data["sales_by_hour"]

        sold = [
            row["hour"]
            for row in hours
            if row["total"] > 0
        ]

        start = min([8, *sold])
        end = max([21, *sold])

        hour_rows = [
            row
            for row in hours
            if start <= row["hour"] <= end
        ]

        hour_peak = max(
            (row["total"] for row in hour_rows),
            default=0,
        )

        view["hour_bars"] = [
            {
                "label": f"{row['hour']:02d}",
                "total": row["total"],
                "pct": _pct(row["total"], hour_peak),
            }
            for row in hour_rows
        ]

        # เมนูขายดีและสถานะเปิดขาย
        top_max = max(
            (dish["qty"] for dish in data["top_dishes"]),
            default=0,
        )

        view["top_dishes"] = [
            {
                **dish,
                "pct": _pct(dish["qty"], top_max),
                "known": dish["id"] in availability,
                "available": availability.get(
                    dish["id"],
                    True,
                ),
            }
            for dish in data["top_dishes"]
        ]

        return view