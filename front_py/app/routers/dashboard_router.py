from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Cookie, Form, Query, Request
from fastapi.responses import RedirectResponse

from app.services.menu_service import MenuService
from app.services.stats_service import StatsService
from app.services.template_service import TemplateService

TH_TZ = timezone(timedelta(hours=7))
DAYS_TH = ("จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา.")
MONTHS_TH = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
             "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
METHODS_TH = {"cash": "เงินสด", "qr_bank": "QR พร้อมเพย์"}


def baht(value) -> str:
    """฿12,450 หรือ ฿12,450.50 (แสดงทศนิยมเมื่อมีเศษสตางค์เท่านั้น)"""
    value = float(value or 0)
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    return "฿" + text


def _pct(value: float, maximum: float) -> int:
    """ความสูงของแท่งกราฟเป็น % (มียอด = อย่างน้อย 3% เพื่อให้มองเห็น)"""
    if not maximum or value <= 0:
        return 0
    return max(3, round(value / maximum * 100))


def _trend(change_pct) -> dict:
    if change_pct is None:
        return {"kind": "none"}
    if change_pct == 0:
        return {"kind": "flat"}
    return {"kind": "up" if change_pct > 0 else "down", "value": abs(change_pct)}


class DashboardRouter:
    """หน้าแดชบอร์ดภาพรวมของร้านสำหรับเจ้าของร้าน (ต้องล็อกอิน Admin)

    ไม่ใช้ JavaScript: เรนเดอร์ทั้งหน้าที่ฝั่งเซิร์ฟเวอร์ และรีเฟรชตัวเองทุก 10 วินาที
    ด้วย <meta http-equiv="refresh"> ส่วนสวิตช์ของหมดเป็นฟอร์ม POST แล้ว redirect กลับ
    """

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

        self.router.add_api_route("", self.show_dashboard, methods=["GET"])
        self.router.add_api_route("/", self.show_dashboard, methods=["GET"], include_in_schema=False)
        self.router.add_api_route(
            "/availability/{item_id}", self.set_availability, methods=["POST"]
        )

    @staticmethod
    def _is_admin(admin_token: str | None) -> bool:
        return admin_token == "logged_in"

    # ---------- หน้าแดชบอร์ด ----------

    async def show_dashboard(
        self, request: Request,
        show_all: int = Query(0, alias="all"),
        admin_token: str | None = Cookie(None),
    ):
        if not self._is_admin(admin_token):
            return RedirectResponse("/admin/login", status_code=303)

        error = None
        data = None
        try:
            data = await self.stats_service.get_dashboard()
        except httpx.HTTPError:
            error = "ติดต่อเซิร์ฟเวอร์หลังบ้านไม่ได้ กรุณาตรวจสอบว่า Backend (พอร์ต 8000) เปิดอยู่"

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
        response = self.template_service.render(request, "dashboard.html", context)
        response.headers["Cache-Control"] = "no-store"
        return response

    # ---------- เปิด/ปิดของหมด (ฟอร์ม POST) ----------

    async def set_availability(
        self, item_id: int,
        available: str = Form(...),
        show_all: int = Form(0),
        admin_token: str | None = Cookie(None),
    ):
        if not self._is_admin(admin_token):
            return RedirectResponse("/admin/login", status_code=303)
        try:
            await self.stats_service.set_availability(item_id, available == "1")
        except httpx.HTTPError:
            pass  # หน้าที่โหลดใหม่จะแสดงสถานะจริงอยู่แล้ว
        suffix = "?all=1" if show_all else ""
        return RedirectResponse(f"/admin/dashboard{suffix}", status_code=303)

    # ---------- แปลงข้อมูลดิบเป็นข้อมูลพร้อมแสดงผล ----------

    def _build_view(self, data: dict | None, menu: list) -> dict:
        now = datetime.now(TH_TZ)
        today_label = f"{DAYS_TH[now.weekday()]} {now.day} {MONTHS_TH[now.month - 1]} {now.year + 543}"

        menu_rows = [
            {"id": m.id, "name": m.name, "category": m.category,
             "price": m.price, "available": m.available}
            for m in menu
        ]
        availability = {m["id"]: m["available"] for m in menu_rows}

        view = {
            "today_label": today_label,
            "updated_at": now.strftime("%H:%M:%S"),
            "menu": menu_rows,
            "has_data": data is not None,
        }
        if data is None:
            data = {
                "revenue": {"today": 0, "yesterday": 0, "change_pct": None},
                "bills": {"today": 0, "yesterday": 0, "change_pct": None},
                "tables": {"active": 0, "total": 0, "live": []},
                "top_dish": None, "top_dishes": [],
                "recent_transactions": [], "sales_trend": [], "sales_by_hour": [],
            }

        view["revenue"] = {**data["revenue"], "trend": _trend(data["revenue"]["change_pct"])}
        view["bills"] = {**data["bills"], "trend": _trend(data["bills"]["change_pct"])}
        view["top_dish"] = data["top_dish"]

        # โต๊ะ: แสดงทุกโต๊ะตามจำนวนที่ตั้งไว้ + โต๊ะที่มีบิลแต่เลขเกินจำนวน
        live = {t["table"]: t for t in data["tables"]["live"]}
        numbers = sorted(set(range(1, data["tables"]["total"] + 1)) | set(live))
        total = data["tables"]["total"]
        active = data["tables"]["active"]
        view["tables"] = {
            "active": active,
            "total": total,
            "free": max(0, total - active),
            "bar": min(100, round(active / total * 100)) if total else 0,
            "tiles": [
                {"number": n, "live": live.get(n),
                 "shown": live[n]["items"][:4] if n in live else [],
                 "more": max(0, len(live[n]["items"]) - 4) if n in live else 0}
                for n in numbers
            ],
        }

        # เงินเข้าล่าสุด
        view["transactions"] = [
            {
                **t,
                "time": datetime.fromisoformat(t["created_at"]).astimezone(TH_TZ).strftime("%H:%M:%S"),
                "method_name": METHODS_TH.get(t["method"], t["method"]),
            }
            for t in data["recent_transactions"]
        ]

        # กราฟยอดขาย 7 วัน
        trend = data["sales_trend"]
        peak = max((d["total"] for d in trend), default=0)
        view["trend_bars"] = []
        for i, d in enumerate(trend):
            day = datetime.strptime(d["date"], "%Y-%m-%d")
            view["trend_bars"].append({
                "label": f"{DAYS_TH[day.weekday()]} {day.day}",
                "total": d["total"],
                "pct": _pct(d["total"], peak),
                "is_today": i == len(trend) - 1,
            })

        # กราฟรายชั่วโมง (ตัดช่วงเช้ามืด/ดึกที่ไม่มียอดออก)
        hours = data["sales_by_hour"]
        sold = [h["hour"] for h in hours if h["total"] > 0]
        start, end = min([8, *sold]), max([21, *sold])
        hour_rows = [h for h in hours if start <= h["hour"] <= end]
        hour_peak = max((h["total"] for h in hour_rows), default=0)
        view["hour_bars"] = [
            {"label": f"{h['hour']:02d}", "total": h["total"], "pct": _pct(h["total"], hour_peak)}
            for h in hour_rows
        ]

        # Top 5 + สถานะเปิด/ปิดขาย
        top_max = max((d["qty"] for d in data["top_dishes"]), default=0)
        view["top_dishes"] = [
            {**d, "pct": _pct(d["qty"], top_max),
             "known": d["id"] in availability,
             "available": availability.get(d["id"], True)}
            for d in data["top_dishes"]
        ]
        return view