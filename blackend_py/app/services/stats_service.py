from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.db import db


TH_TZ = timezone(timedelta(hours=7), name="ICT")
VALID_KITCHEN_STATES = {"cooking", "ready", "served"}
VALID_TABLE_STATES = {"dining", "waiting_payment"}
VALID_PAYMENT_METHODS = {"cash", "promptpay_qr"}


class StatsService:
    """Persist order and payment records in the project's Firestore database."""

    def __init__(self, firestore=None):
        self.db = firestore or db
        self.orders = self.db.collection("order_events")
        self.transactions = self.db.collection("transactions")
        self.live_orders = self.db.collection("live_orders")

    @staticmethod
    def _now():
        return datetime.now(TH_TZ)

    @staticmethod
    def _clean_items(items):
        cleaned = []
        for item in items:
            qty = int(item["qty"])
            price = round(float(item["price"]), 2)
            if qty <= 0 or price < 0:
                raise ValueError("จำนวนและราคาอาหารไม่ถูกต้อง")
            cleaned.append({
                "id": int(item["id"]), "name": str(item["name"]),
                "category": str(item.get("category", "อื่นๆ")),
                "price": price, "qty": qty,
            })
        return cleaned

    def place_order(self, table: int, items: list[dict]):
        if not 1 <= int(table) <= 30:
            raise ValueError("หมายเลขโต๊ะต้องอยู่ระหว่าง 1 ถึง 30")
        items = self._clean_items(items)
        if not items:
            raise ValueError("ไม่มีรายการอาหาร")
        now = self._now()
        live_ref = self.live_orders.document(str(table))
        current = live_ref.get()
        live = current.to_dict() if current.exists else None
        if live and live.get("status") == "paid":
            raise ValueError("โต๊ะนี้ชำระเงินแล้ว กรุณาให้พนักงานเคลียร์โต๊ะก่อน")

        existing = {int(item["id"]): item for item in (live or {}).get("items", [])}
        for item in items:
            old = existing.get(item["id"])
            if old:
                old["qty"] += item["qty"]
            else:
                existing[item["id"]] = {**item, "kitchen_status": "cooking"}

        opened_at = (live or {}).get("opened_at", now.isoformat(timespec="seconds"))
        live_ref.set({
            "table": int(table), "status": "dining", "opened_at": opened_at,
            "updated_at": now.isoformat(timespec="seconds"),
            "items": list(existing.values()),
        })
        self.orders.document().set({
            "table": int(table), "items": items,
            "created_at": now.isoformat(timespec="seconds"),
            "date": now.date().isoformat(),
        })
        return {"status": "success"}

    def set_table_status(self, table: int, status: str):
        if status not in VALID_TABLE_STATES:
            raise ValueError("สถานะโต๊ะไม่ถูกต้อง")
        ref = self.live_orders.document(str(table))
        snapshot = ref.get()
        if not snapshot.exists or (snapshot.to_dict() or {}).get("status") == "paid":
            raise ValueError("ไม่พบโต๊ะที่ยังเปิดใช้งาน")
        ref.update({"status": status, "updated_at": self._now().isoformat(timespec="seconds")})
        return {"status": "success"}

    def set_kitchen_status(self, table: int, item_id: int, status: str):
        if status not in VALID_KITCHEN_STATES:
            raise ValueError("สถานะอาหารไม่ถูกต้อง")
        ref = self.live_orders.document(str(table))
        snapshot = ref.get()
        if not snapshot.exists:
            raise ValueError("ไม่พบรายการอาหาร")
        live = snapshot.to_dict() or {}
        found = False
        for item in live.get("items", []):
            if int(item["id"]) == item_id:
                item["kitchen_status"] = status
                found = True
                break
        if not found:
            raise ValueError("ไม่พบรายการอาหาร")
        live["updated_at"] = self._now().isoformat(timespec="seconds")
        ref.set(live)
        return {"status": "success"}

    def record_payment(self, table: int, method: str):
        if method not in VALID_PAYMENT_METHODS:
            raise ValueError("วิธีชำระเงินไม่ถูกต้อง")
        ref = self.live_orders.document(str(table))
        snapshot = ref.get()
        if not snapshot.exists:
            raise ValueError("ไม่พบโต๊ะนี้")
        live = snapshot.to_dict() or {}
        if live.get("status") != "waiting_payment":
            raise ValueError("โต๊ะนี้ยังไม่ได้เรียกเก็บเงิน")
        items = self._clean_items(live.get("items", []))
        if not items:
            raise ValueError("ไม่พบรายการอาหาร")
        now = self._now()
        amount = round(sum(item["price"] * item["qty"] for item in items), 2)
        tx_ref = self.transactions.document()
        tx_ref.set({
            "table": int(table), "method": method, "amount": amount,
            "items": items, "bill_closed": True, "payment_type": "full",
            "status": "paid", "created_at": now.isoformat(timespec="seconds"),
            "date": now.date().isoformat(),
        })
        live.update({"status": "paid", "updated_at": now.isoformat(timespec="seconds")})
        ref.set(live)
        return {"status": "success", "id": tx_ref.id}

    def reset_table(self, table: int):
        ref = self.live_orders.document(str(table))
        snapshot = ref.get()
        if not snapshot.exists or (snapshot.to_dict() or {}).get("status") != "paid":
            raise ValueError("เคลียร์โต๊ะได้หลังบันทึกการชำระเงินแล้วเท่านั้น")
        ref.delete()
        return {"status": "success"}

    def dashboard_data(self, total_tables: int = 10):
        now = self._now()
        today = now.date().isoformat()
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        day_labels = [(now.date() - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        transactions = []
        for snap in self.transactions.stream():
            tx = snap.to_dict() or {}
            tx["id"] = snap.id
            try:
                tx_dt = datetime.fromisoformat(tx.get("created_at", ""))
                if tx_dt.tzinfo is None:
                    tx_dt = tx_dt.replace(tzinfo=TH_TZ)
                tx["_datetime"] = tx_dt.astimezone(TH_TZ)
            except ValueError:
                continue
            transactions.append(tx)

        revenue_by_day = defaultdict(float)
        bills_by_day = defaultdict(int)
        category_totals = defaultdict(float)
        for tx in transactions:
            key = tx["_datetime"].date().isoformat()
            revenue_by_day[key] += float(tx.get("amount", 0))
            bills_by_day[key] += 1
            if key == today:
                for item in tx.get("items", []):
                    category_totals[item.get("category", "อื่นๆ")] += float(item.get("price", 0)) * int(item.get("qty", 0))

        order_events = []
        for snap in self.orders.stream():
            event = snap.to_dict() or {}
            order_events.append(event)
        all_popular = defaultdict(int)
        daily_popular = defaultdict(int)
        for event in order_events:
            event_date = event.get("date")
            for item in event.get("items", []):
                key = (int(item["id"]), str(item["name"]))
                all_popular[key] += int(item.get("qty", 0))
                if event_date == today:
                    daily_popular[key] += int(item.get("qty", 0))

        popular = [{"id": key[0], "name": key[1], "qty": qty} for key, qty in sorted(all_popular.items(), key=lambda pair: (-pair[1], pair[0][1]))[:5]]
        daily_top = sorted(daily_popular.items(), key=lambda pair: (-pair[1], pair[0][1]))
        live_tables = []
        for snap in self.live_orders.stream():
            live = snap.to_dict() or {}
            items = live.get("items", [])
            live_tables.append({
                "table": int(live.get("table", snap.id)),
                "status": live.get("status", "dining"),
                "opened_at": live.get("opened_at", ""),
                "items": items,
                "total": round(sum(float(item.get("price", 0)) * int(item.get("qty", 0)) for item in items), 2),
            })
        live_tables.sort(key=lambda item: item["table"])

        recent = sorted(transactions, key=lambda tx: tx["_datetime"], reverse=True)[:10]
        for tx in recent:
            tx["time"] = tx["_datetime"].strftime("%H:%M")
            tx.pop("_datetime", None)
        category_sum = sum(category_totals.values())
        categories = [{"category": name, "total": total, "pct": round(total / category_sum * 100) if category_sum else 0} for name, total in sorted(category_totals.items())]
        trend = [{"date": label, "total": round(revenue_by_day[label], 2)} for label in day_labels]
        trend_max = max((day["total"] for day in trend), default=0)
        for day in trend:
            day["pct"] = round(day["total"] / trend_max * 100) if trend_max else 0

        today_top = daily_top[0] if daily_top else None
        return {
            "today": today,
            "revenue": round(revenue_by_day[today], 2),
            "bills": bills_by_day[today],
            "revenue_yesterday": round(revenue_by_day[yesterday], 2),
            "bills_yesterday": bills_by_day[yesterday],
            "active_tables": len(live_tables), "total_tables": total_tables,
            "top_dish": ({"id": today_top[0][0], "name": today_top[0][1], "qty": today_top[1]} if today_top else None),
            "popular": popular, "trend": trend, "trend_max": trend_max,
            "categories": categories, "live_tables": live_tables, "transactions": recent,
        }
