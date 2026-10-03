from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.db import db

# เวลาไทย (UTC+7) -- กำหนดเองเพื่อไม่ต้องพึ่ง tzdata บน Windows
TH_TZ = timezone(timedelta(hours=7))

# id พิเศษที่หน้าบ้านใช้แทน "ส่วนแบ่งของกลาง" ตอนแยกจ่าย ไม่ใช่เมนูจริง
SHARED_PSEUDO_ID = 9999


def _now() -> datetime:
    return datetime.now(TH_TZ)


def _day(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


class StatsService:
    """เก็บและสรุปสถิติของร้านใน Firestore สำหรับหน้าแดชบอร์ดของเจ้าของร้าน

    collections:
      - transactions : เงินเข้าแต่ละครั้ง (1 บิลอาจมีหลายรายการถ้าแยกจ่าย)
      - order_events : อาหารที่ลูกค้าส่งเข้าครัวแต่ละรอบ (ใช้จัดอันดับเมนูขายดี)
      - live_orders  : บิลที่ยังเปิดอยู่ของแต่ละโต๊ะ (1 เอกสารต่อ 1 โต๊ะ)

    ทุก query ใช้ equality บนฟิลด์ "date" อย่างเดียว จึงไม่ต้องสร้าง composite index
    """

    def __init__(self):
        self.db = db
        self.transactions = "transactions"
        self.order_events = "order_events"
        self.live_orders = "live_orders"

    # ---------- เขียนข้อมูล ----------

    def record_order(self, table: int | None, items: list[dict]) -> dict:
        """บันทึกว่าลูกค้าส่งอาหารเข้าครัวรอบนี้"""
        now = _now()
        doc = {
            "table": table,
            "items": [self._clean_item(i) for i in items],
            "created_at": now.isoformat(),
            "date": _day(now),
        }
        self.db.collection(self.order_events).document().set(doc)
        return doc

    def record_transaction(
        self, table: int | None, method: str, amount: float,
        items: list[dict], bill_closed: bool,
    ) -> dict:
        """บันทึกเงินเข้า 1 รายการ bill_closed=True คือจ่ายครบและปิดบิลของโต๊ะแล้ว"""
        now = _now()
        doc = {
            "table": table,
            "method": method,
            "amount": round(float(amount), 2),
            "items": [self._clean_item(i) for i in items],
            "bill_closed": bool(bill_closed),
            "created_at": now.isoformat(),
            "date": _day(now),
        }
        ref = self.db.collection(self.transactions).document()
        ref.set(doc)
        return {"id": ref.id, **doc}

    def set_live_order(self, table: int, items: list[dict]) -> None:
        """อัปเดตบิลที่เปิดอยู่ของโต๊ะ ถ้าไม่มีรายการเหลือ = โต๊ะว่าง ให้ลบทิ้ง"""
        ref = self.db.collection(self.live_orders).document(str(table))
        clean = [self._clean_item(i) for i in items if int(i.get("qty", 0)) > 0]
        if not clean:
            ref.delete()
            return
        existing = ref.get()
        opened_at = (existing.to_dict() or {}).get("opened_at") if existing.exists else None
        now = _now().isoformat()
        ref.set({
            "table": table,
            "items": clean,
            "opened_at": opened_at or now,
            "updated_at": now,
        })

    @staticmethod
    def _clean_item(item: dict) -> dict:
        return {
            "id": int(item["id"]),
            "name": str(item["name"]),
            "price": float(item["price"]),
            "qty": int(item["qty"]),
        }

    # ---------- อ่านข้อมูล / สรุปผล ----------

    def get_dashboard(self, days: int = 7) -> dict:
        now = _now()
        today = _day(now)
        yesterday = _day(now - timedelta(days=1))
        day_keys = [_day(now - timedelta(days=n)) for n in range(days - 1, -1, -1)]

        tx_by_day = self._transactions_by_day(day_keys)
        today_tx = tx_by_day.get(today, [])
        yesterday_tx = tx_by_day.get(yesterday, [])

        revenue_today = round(sum(t["amount"] for t in today_tx), 2)
        revenue_yesterday = round(sum(t["amount"] for t in yesterday_tx), 2)
        bills_today = sum(1 for t in today_tx if t.get("bill_closed"))
        bills_yesterday = sum(1 for t in yesterday_tx if t.get("bill_closed"))

        top_dishes = self._top_dishes(today, limit=5)
        live = self._live_tables()

        return {
            "generated_at": now.isoformat(),
            "revenue": {
                "today": revenue_today,
                "yesterday": revenue_yesterday,
                "change_pct": self._change_pct(revenue_today, revenue_yesterday),
            },
            "bills": {
                "today": bills_today,
                "yesterday": bills_yesterday,
                "change_pct": self._change_pct(bills_today, bills_yesterday),
            },
            "tables": {
                "active": len(live),
                "total": settings.TOTAL_TABLES,
                "live": live,
            },
            "top_dish": top_dishes[0] if top_dishes else None,
            "top_dishes": top_dishes,
            "recent_transactions": [
                self._public_tx(t)
                for t in sorted(today_tx, key=lambda t: t["created_at"], reverse=True)[:10]
            ],
            "sales_trend": [
                {"date": d, "total": round(sum(t["amount"] for t in tx_by_day.get(d, [])), 2)}
                for d in day_keys
            ],
            "sales_by_hour": self._sales_by_hour(today_tx),
        }

    def _transactions_by_day(self, day_keys: list[str]) -> dict[str, list[dict]]:
        # Firestore "in" รองรับสูงสุด 30 ค่า เรียกแค่ 7 วันจึงพอ
        docs = self.db.collection(self.transactions).where("date", "in", day_keys).stream()
        grouped: dict[str, list[dict]] = defaultdict(list)
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            grouped[data["date"]].append(data)
        return grouped

    def _top_dishes(self, day: str, limit: int) -> list[dict]:
        docs = self.db.collection(self.order_events).where("date", "==", day).stream()
        counts: dict[int, dict] = {}
        for doc in docs:
            for item in doc.to_dict().get("items", []):
                if item["id"] == SHARED_PSEUDO_ID:
                    continue
                row = counts.setdefault(item["id"], {"id": item["id"], "name": item["name"], "qty": 0})
                row["qty"] += item["qty"]
        ranked = sorted(counts.values(), key=lambda r: (-r["qty"], r["id"]))
        return ranked[:limit]

    def _live_tables(self) -> list[dict]:
        tables = []
        for doc in self.db.collection(self.live_orders).stream():
            data = doc.to_dict()
            items = data.get("items", [])
            if not items:
                continue
            tables.append({
                "table": data.get("table"),
                "items": items,
                "total": round(sum(i["price"] * i["qty"] for i in items), 2),
                "item_count": sum(i["qty"] for i in items),
                "opened_at": data.get("opened_at"),
            })
        tables.sort(key=lambda t: (t["table"] is None, t["table"]))
        return tables

    @staticmethod
    def _sales_by_hour(today_tx: list[dict]) -> list[dict]:
        totals = [0.0] * 24
        for t in today_tx:
            hour = datetime.fromisoformat(t["created_at"]).astimezone(TH_TZ).hour
            totals[hour] += t["amount"]
        return [{"hour": h, "total": round(v, 2)} for h, v in enumerate(totals)]

    @staticmethod
    def _public_tx(t: dict) -> dict:
        return {
            "id": t["id"],
            "table": t.get("table"),
            "method": t.get("method"),
            "amount": t["amount"],
            "bill_closed": t.get("bill_closed", False),
            "created_at": t["created_at"],
            "item_count": sum(i["qty"] for i in t.get("items", [])),
        }

    @staticmethod
    def _change_pct(today: float, yesterday: float) -> float | None:
        """เปลี่ยนแปลงเทียบเมื่อวานเป็น % -- None ถ้าเมื่อวานเป็น 0 (เทียบไม่ได้)"""
        if not yesterday:
            return None
        return round((today - yesterday) / yesterday * 100, 1)