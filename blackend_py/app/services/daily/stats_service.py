from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.cloud.firestore import transactional

from app.core.db import db
from app.services.table_settings_service import TableSettingsService

# เวลาไทย UTC+7
TH_TZ = timezone(timedelta(hours=7))

# รายการพิเศษสำหรับส่วนแบ่งของกลาง ไม่ใช่เมนูจริง
SHARED_PSEUDO_ID = 9999


def _now() -> datetime:
    return datetime.now(TH_TZ)


def _day(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


class StatsService:
    """เก็บและสรุปสถิติของร้านใน Firestore สำหรับแดชบอร์ด"""

    def __init__(self):
        self.db = db
        self.transactions = "transactions"
        self.order_events = "order_events"
        self.live_orders = "live_orders"

    # ---------- บันทึกออเดอร์ ----------

    def record_order(
        self,
        table: int | None,
        items: list[dict],
    ) -> dict:
        """บันทึกรายการอาหารที่ส่งเข้าครัวแต่ละรอบ"""
        now = _now()

        doc = {
            "table": table,
            "items": [self._clean_item(i) for i in items],
            "created_at": now.isoformat(),
            "date": _day(now),
        }

        self.db.collection(self.order_events).document().set(doc)
        return doc

    # ---------- บันทึกการชำระเงิน ----------

    def record_transaction(
        self,
        table: int | None,
        method: str,
        amount: float,
        items: list[dict],
        bill_closed: bool,
        payment_type: str | None = None,
    ) -> dict:
        """บันทึกเงินเข้าและรูปแบบการจ่าย

        payment_type:
            full = บิลรวม
            split = แยกจ่ายรายคน
            None = ไม่ระบุรูปแบบ

        bill_closed ระบุว่ารายการนี้ทำให้บิลปิดหรือไม่
        แยกจาก payment_type เพราะการแยกจ่ายก็ปิดบิลได้
        """
        if payment_type not in (None, "full", "split"):
            raise ValueError("Invalid payment type")

        now = _now()

        doc = {
            "table": table,
            "method": method,
            "amount": round(float(amount), 2),
            "items": [self._clean_item(i) for i in items],
            "bill_closed": bool(bill_closed),
            "payment_type": payment_type,
            "created_at": now.isoformat(),
            "date": _day(now),
        }

        ref = self.db.collection(self.transactions).document()
        ref.set(doc)

        return {"id": ref.id, **doc}

    # ---------- อัปเดตบิลและสถานะโต๊ะ ----------

    def set_live_order(
        self,
        table: int,
        items: list[dict],
        status: str | None = None,
    ) -> None:
        """อัปเดตบิล สถานะโต๊ะ และรักษาสถานะอาหาร

        dining = กำลังรับประทาน
        waiting_payment = รอชำระ

        เมนูใหม่หรือจำนวนเพิ่ม เริ่มที่ cooking
        จำนวนเท่าเดิมหรือลดลง รักษาสถานะอาหารเดิม

        items ว่างยังลบโต๊ะตามพฤติกรรมเดิม
        หลังจ่ายครบต้องเรียก mark_table_paid แทนส่ง items ว่าง
        เพื่อเก็บโต๊ะไว้จนพนักงานกด Reset
        """
        if status not in (None, "dining", "waiting_payment"):
            raise ValueError("Invalid table status")

        ref = self.db.collection(self.live_orders).document(str(table))

        clean = [
            self._clean_item(i)
            for i in items
            if int(i.get("qty", 0)) > 0
        ]

        @transactional
        def save(transaction):
            existing = ref.get(transaction=transaction)

            previous = (
                (existing.to_dict() or {})
                if existing.exists
                else {}
            )

            if not clean:
                transaction.delete(ref)
                return

            previous_items = {
                i["id"]: i
                for i in previous.get("items", [])
            }

            merged = []

            for item in clean:
                old = previous_items.get(item["id"])
                kitchen_status = "cooking"

                if old and item["qty"] <= old["qty"]:
                    kitchen_status = old.get(
                        "kitchen_status",
                        "cooking",
                    )

                merged.append({
                    **item,
                    "kitchen_status": kitchen_status,
                })

            now = _now().isoformat()

            # เขียนบิลที่ยังมีรายการค้างชำระ
            # ไม่คง paid=True จากบิลที่จ่ายครบไปแล้ว
            transaction.set(ref, {
                "table": table,
                "items": merged,
                "status": status or previous.get("status", "dining"),
                "opened_at": previous.get("opened_at") or now,
                "updated_at": now,
            })

        save(self.db.transaction())

    # ---------- ชำระครบ รอเคลียร์โต๊ะ ----------

    def mark_table_paid(
        self,
        table: int,
        paid_items: list[dict],
    ) -> None:
        """เรียกหลังยืนยันว่าชำระครบแล้วเท่านั้น

        ล้างรายการค้างชำระ แต่เก็บโต๊ะไว้เป็น paid=True
        เพื่อให้พนักงานกด Reset หลังลูกค้าลุกออก

        ตรวจรายการปัจจุบันกับรายการที่ชำระ
        ป้องกันล้างออเดอร์ใหม่ที่เพิ่มระหว่างชำระเงิน
        """
        ref = self.db.collection(self.live_orders).document(str(table))

        @transactional
        def save(transaction):
            snapshot = ref.get(transaction=transaction)

            previous = (
                (snapshot.to_dict() or {})
                if snapshot.exists
                else {}
            )

            quantities = defaultdict(int)

            for item in paid_items:
                quantities[int(item["id"])] += int(item["qty"])

            has_unpaid_orders = any(
                item["qty"] > quantities[item["id"]]
                for item in previous.get("items", [])
            )

            if has_unpaid_orders:
                raise ValueError("New unpaid orders exist")

            now = _now().isoformat()

            transaction.set(ref, {
                "table": table,
                "items": [],
                "status": "waiting_payment",
                "paid": True,
                "opened_at": previous.get("opened_at") or now,
                "updated_at": now,
            })

        save(self.db.transaction())

    # ---------- Reset Table ----------

    def reset_table(
        self,
        table: int,
        opened_at: str,
    ) -> bool:
        """เคลียร์เฉพาะโต๊ะที่ชำระครบแล้ว

        ตรวจ opened_at ว่ายังเป็นบิลเดียวกับที่พนักงานเปิดดู
        ลบเฉพาะ live_orders ไม่ลบประวัติยอดขายหรือการชำระเงิน

        คืน False เมื่อโต๊ะว่างอยู่แล้ว
        """
        ref = self.db.collection(self.live_orders).document(str(table))

        @transactional
        def reset(transaction):
            snapshot = ref.get(transaction=transaction)

            if not snapshot.exists:
                return False

            data = snapshot.to_dict() or {}

            if data.get("opened_at") != opened_at:
                raise ValueError("Table bill has changed")

            if not data.get("paid") or data.get("items"):
                raise ValueError("Table is not fully paid")

            transaction.delete(ref)
            return True

        return reset(self.db.transaction())

    # ---------- อัปเดตสถานะอาหาร ----------

    def set_kitchen_status(
        self,
        table: int,
        item_id: int,
        status: str,
        expected_qty: int,
        opened_at: str,
    ) -> dict | None:
        """เปลี่ยนสถานะอาหารทั้งแถวเมนู

        cooking = กำลังทำ
        ready = พร้อมเสิร์ฟ
        served = เสิร์ฟแล้ว

        ตรวจว่าบิลและจำนวนยังตรงกับหน้าที่พนักงานเปิดอยู่
        """
        if status not in ("cooking", "ready", "served"):
            raise ValueError("Invalid kitchen status")

        ref = self.db.collection(self.live_orders).document(str(table))

        @transactional
        def update(transaction):
            snapshot = ref.get(transaction=transaction)

            if not snapshot.exists:
                return None

            data = snapshot.to_dict() or {}

            if data.get("opened_at") != opened_at:
                raise ValueError("Table bill has changed")

            items = [
                dict(item)
                for item in data.get("items", [])
            ]

            item = next(
                (i for i in items if i["id"] == item_id),
                None,
            )

            if item is None:
                return None

            if item["qty"] != expected_qty:
                raise ValueError("Order quantity has changed")

            item["kitchen_status"] = status

            transaction.update(ref, {
                "items": items,
                "updated_at": _now().isoformat(),
            })

            return item

        return update(self.db.transaction())

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

        day_keys = [
            _day(now - timedelta(days=n))
            for n in range(days - 1, -1, -1)
        ]

        tx_by_day = self._transactions_by_day(day_keys)
        today_tx = tx_by_day.get(today, [])
        yesterday_tx = tx_by_day.get(yesterday, [])

        revenue_today = round(
            sum(t["amount"] for t in today_tx),
            2,
        )

        revenue_yesterday = round(
            sum(t["amount"] for t in yesterday_tx),
            2,
        )

        bills_today = sum(
            1 for t in today_tx if t.get("bill_closed")
        )

        bills_yesterday = sum(
            1 for t in yesterday_tx if t.get("bill_closed")
        )

        top_dishes = self._top_dishes(today, limit=5)
        live = self._live_tables()

        return {
            "generated_at": now.isoformat(),
            "revenue": {
                "today": revenue_today,
                "yesterday": revenue_yesterday,
                "change_pct": self._change_pct(
                    revenue_today,
                    revenue_yesterday,
                ),
            },
            "bills": {
                "today": bills_today,
                "yesterday": bills_yesterday,
                "change_pct": self._change_pct(
                    bills_today,
                    bills_yesterday,
                ),
            },
            "tables": {
                # รวมโต๊ะชำระแล้วที่ยังรอพนักงานเคลียร์
                "active": len(live),

                # อ่านจำนวนโต๊ะที่บันทึกจากหน้า Admin
                "total": TableSettingsService().get_count(),

                "live": live,
            },
            "top_dish": top_dishes[0] if top_dishes else None,
            "top_dishes": top_dishes,
            "recent_transactions": [
                self._public_tx(t)
                for t in sorted(
                    today_tx,
                    key=lambda t: t["created_at"],
                    reverse=True,
                )[:10]
            ],
            "sales_trend": [
                {
                    "date": d,
                    "total": round(
                        sum(
                            t["amount"]
                            for t in tx_by_day.get(d, [])
                        ),
                        2,
                    ),
                }
                for d in day_keys
            ],
            "sales_by_hour": self._sales_by_hour(today_tx),
        }

    def _transactions_by_day(
        self,
        day_keys: list[str],
    ) -> dict[str, list[dict]]:
        docs = (
            self.db.collection(self.transactions)
            .where("date", "in", day_keys)
            .stream()
        )

        grouped: dict[str, list[dict]] = defaultdict(list)

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            grouped[data["date"]].append(data)

        return grouped

    def _top_dishes(
        self,
        day: str,
        limit: int,
    ) -> list[dict]:
        docs = (
            self.db.collection(self.order_events)
            .where("date", "==", day)
            .stream()
        )

        counts: dict[int, dict] = {}

        for doc in docs:
            for item in doc.to_dict().get("items", []):
                if item["id"] == SHARED_PSEUDO_ID:
                    continue

                row = counts.setdefault(
                    item["id"],
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "qty": 0,
                    },
                )

                row["qty"] += item["qty"]

        ranked = sorted(
            counts.values(),
            key=lambda r: (-r["qty"], r["id"]),
        )

        return ranked[:limit]

    def _live_tables(self) -> list[dict]:
        tables = []

        for doc in self.db.collection(self.live_orders).stream():
            data = doc.to_dict()

            items = [
                {
                    **item,
                    "kitchen_status": item.get(
                        "kitchen_status",
                        "cooking",
                    ),
                }
                for item in data.get("items", [])
            ]

            paid = bool(data.get("paid", False))

            # โต๊ะจ่ายครบยังแสดงจนกว่าพนักงานจะกด Reset
            if not items and not paid:
                continue

            tables.append({
                "table": data.get("table"),
                "status": data.get("status", "dining"),
                "paid": paid,
                "items": items,
                "total": round(
                    sum(i["price"] * i["qty"] for i in items),
                    2,
                ),
                "item_count": sum(i["qty"] for i in items),
                "opened_at": data.get("opened_at"),
            })

        tables.sort(
            key=lambda t: (
                t["table"] is None,
                t["table"],
            )
        )

        return tables

    @staticmethod
    def _sales_by_hour(today_tx: list[dict]) -> list[dict]:
        totals = [0.0] * 24

        for t in today_tx:
            hour = (
                datetime.fromisoformat(t["created_at"])
                .astimezone(TH_TZ)
                .hour
            )

            totals[hour] += t["amount"]

        return [
            {"hour": h, "total": round(v, 2)}
            for h, v in enumerate(totals)
        ]

    @staticmethod
    def _public_tx(t: dict) -> dict:
        return {
            "id": t["id"],
            "table": t.get("table"),
            "method": t.get("method"),
            "amount": t["amount"],
            "bill_closed": t.get("bill_closed", False),

            # ข้อมูลเก่าที่ไม่มี field นี้จะคืน None
            "payment_type": t.get("payment_type"),

            "created_at": t["created_at"],
            "item_count": sum(
                i["qty"] for i in t.get("items", [])
            ),
        }

    @staticmethod
    def _change_pct(
        today: float,
        yesterday: float,
    ) -> float | None:
        if not yesterday:
            return None

        return round((today - yesterday) / yesterday * 100, 1)