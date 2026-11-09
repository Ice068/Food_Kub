from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib

from google.cloud.firestore import transactional

from app.core.db import db
from app.services.table_settings_service import TableSettingsService


TH_TZ = timezone(timedelta(hours=7))

TABLE_BILL_CHANGED = "Table bill has changed"

# รายการพิเศษสำหรับส่วนแบ่งของกลาง
SHARED_PSEUDO_ID = 9999


def _now() -> datetime:
    return datetime.now(TH_TZ)


def _day(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class LiveOrderUpdate:
    table: int
    items: list[dict]
    status: str | None
    shared_paid: float
    expected_opened_at: str | None
    expected_updated_at: str | None
    shared_item_ids: list[int] = ()


@dataclass(frozen=True)
class FullBillPayment:
    table: int
    opened_at: str
    expected_items: list[dict]
    action: str
    method: str | None
    expected_total: float | None


class StatsService:
    """เก็บออเดอร์ การชำระเงิน และสถานะโต๊ะใน Firestore"""

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
        """บันทึกเงินเข้า พร้อมรูปแบบการชำระและสถานะปิดบิล"""
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
        shared_paid: float = 0,
        shared_item_ids: list[int] | None = None,
        expected_opened_at: str | None = None,
        expected_updated_at: str | None = None,
    ) -> None:
        """ตรวจรุ่นข้อมูลก่อนเขียน และคงสถานะครัวเดิม"""
        if status not in (None, "dining", "waiting_payment"):
            raise ValueError("Invalid table status")

        ref = self.db.collection(self.live_orders).document(
            str(table)
        )

        clean = [
            self._clean_item(item)
            for item in items
            if int(item.get("qty", 0)) > 0
        ]

        order = LiveOrderUpdate(
            table=table,
            items=clean,
            status=status,
            shared_paid=shared_paid,
            expected_opened_at=expected_opened_at,
            expected_updated_at=expected_updated_at,
            shared_item_ids=list(shared_item_ids or []),
        )

        @transactional
        def save(transaction):
            self._save_live_order(
                transaction,
                ref,
                order,
            )

        save(self.db.transaction())

    def _save_live_order(
        self,
        transaction,
        ref,
        order,
    ):
        snapshot = ref.get(transaction=transaction)

        previous = (
            (snapshot.to_dict() or {})
            if snapshot.exists
            else {}
        )

        if previous.get("paid"):
            raise ValueError(
                "Table is paid; reset before accepting orders"
            )

        if not order.items:
            return

        self._validate_live_order_version(
            previous,
            order.status,
            order.expected_opened_at,
            order.expected_updated_at,
        )

        previous_items = {
            item["id"]: item
            for item in previous.get("items", [])
        }

        merged = [
            self._with_kitchen_status(
                item,
                previous_items.get(item["id"]),
            )
            for item in order.items
        ]

        now = _now().isoformat()

        persisted_shared_ids = (
            list(order.shared_item_ids)
            if order.shared_item_ids
            else previous.get("shared_item_ids", [])
        )

        transaction.set(ref, {
            "table": order.table,
            "items": merged,
            "shared_paid": order.shared_paid,
            "shared_item_ids": persisted_shared_ids,
            "status": (
                order.status
                or previous.get("status", "dining")
            ),
            "opened_at": previous.get("opened_at") or now,
            "updated_at": now,
        })

    @staticmethod
    def _validate_live_order_version(
        previous,
        status,
        expected_opened_at,
        expected_updated_at,
    ):
        if (
            previous
            and expected_opened_at is not None
            and previous.get("opened_at") != expected_opened_at
        ):
            raise ValueError(TABLE_BILL_CHANGED)

        if not previous and expected_opened_at:
            raise ValueError("Table was reset")

        if (
            previous
            and expected_updated_at is not None
            and previous.get("updated_at") != expected_updated_at
        ):
            raise ValueError(
                "Order changed; reload before updating"
            )

        if (
            previous.get("status") == "waiting_payment"
            and status == "dining"
            and not (float(previous.get("shared_paid", 0) or 0) > 0)
        ):
            raise ValueError("Table is waiting for payment")

    @staticmethod
    def _with_kitchen_status(item, old):
        kitchen_status = "cooking"

        if old and item["qty"] <= old["qty"]:
            kitchen_status = old.get(
                "kitchen_status",
                "cooking",
            )

        return {
            **item,
            "kitchen_status": kitchen_status,
        }

    # ---------- ชำระครบจากระบบชำระเงิน ----------

    def mark_table_paid(
        self,
        table: int,
        paid_items: list[dict],
    ) -> None:
        """
        เรียกหลังระบบยืนยันการชำระครบแล้วเท่านั้น
        เก็บโต๊ะไว้จนพนักงานกดเคลียร์
        """
        ref = self.db.collection(self.live_orders).document(
            str(table)
        )

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
                "shared_item_ids": [],
            })

        save(self.db.transaction())

    # ---------- อ่านและตรวจสอบบิล ----------

    @staticmethod
    def _bill_signature(items):
        return sorted(
            (
                int(item["id"]),
                int(item["qty"]),
                Decimal(str(item["price"])),
            )
            for item in items
        )

    def get_live_table(self, table):
        snapshot = (
            self.db.collection(self.live_orders)
            .document(str(table))
            .get()
        )

        return (
            snapshot.to_dict()
            if snapshot.exists
            else None
        )

    # ---------- เรียกชำระ / แอดมินยืนยันรับเงิน ----------

    def update_table_payment(
        self,
        table,
        opened_at,
        expected_items,
        action,
        method=None,
        expected_total=None,
    ):
        """บันทึกใบรับเงินและสถานะชำระครบใน transaction เดียวกัน"""
        self._validate_payment_action(action, method)

        ref = self.db.collection(self.live_orders).document(
            str(table)
        )

        receipt_id = "table-" + hashlib.sha256(
            f"{table}:{opened_at}".encode()
        ).hexdigest()

        receipt_ref = (
            self.db.collection(self.transactions)
            .document(receipt_id)
        )

        payment = FullBillPayment(
            table=table,
            opened_at=opened_at,
            expected_items=expected_items,
            action=action,
            method=method,
            expected_total=expected_total,
        )

        @transactional
        def update(transaction):
            return self._update_full_bill(
                transaction,
                ref,
                receipt_ref,
                payment,
            )

        return update(self.db.transaction())

    @staticmethod
    def _validate_payment_action(action, method):
        if action not in (
            "request-payment",
            "confirm-payment",
        ):
            raise ValueError("Invalid action")

        if (
            action == "confirm-payment"
            and method not in ("cash", "qr_bank")
        ):
            raise ValueError("Invalid payment method")

    def _update_full_bill(
        self,
        transaction,
        ref,
        receipt_ref,
        payment,
    ):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            raise LookupError("Table not found")

        data = snapshot.to_dict() or {}

        if data.get("opened_at") != payment.opened_at:
            raise ValueError(TABLE_BILL_CHANGED)

        # ยืนยันซ้ำ คืนผลเดิมโดยไม่บันทึกยอดขายเพิ่ม
        if data.get("paid"):
            return {
                "status": "success",
                "paid": True,
                "payment_id": data.get("payment_id"),
            }

        items = data.get("items", [])

        self._validate_payment_items(
            items,
            payment.expected_items,
        )

        now = _now()

        if payment.action == "request-payment":
            transaction.update(ref, {
                "status": "waiting_payment",
                "updated_at": now.isoformat(),
            })

            return {
                "status": "success",
                "paid": False,
            }

        if data.get("status") != "waiting_payment":
            raise ValueError(
                "Table is not waiting for payment"
            )

        amount = self._validated_outstanding_amount(
            items,
            data.get("shared_paid", 0),
            payment.expected_total,
        )

        is_split = bool(float(data.get("shared_paid", 0) or 0) > 0)

        return self._record_full_payment(
            transaction,
            ref,
            receipt_ref,
            payment,
            items,
            amount,
            now,
            is_split=is_split,
        )

    def _validate_payment_items(
        self,
        items,
        expected_items,
    ):
        if (
            not items
            or self._bill_signature(items)
            != self._bill_signature(expected_items)
        ):
            raise ValueError(TABLE_BILL_CHANGED)

    @staticmethod
    def _validated_outstanding_amount(
        items,
        shared_paid,
        expected_total,
    ):
        gross = sum(
            (
                Decimal(str(item["price"])) * item["qty"]
                for item in items
            ),
            Decimal(0),
        )

        amount = gross - Decimal(str(shared_paid))

        if (
            not amount.is_finite()
            or amount <= 0
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise ValueError("Invalid outstanding amount")

        if (
            expected_total is None
            or Decimal(str(expected_total)) != amount
        ):
            raise ValueError(
                "Outstanding amount has changed"
            )

        return amount

    def _record_full_payment(
        self,
        transaction,
        ref,
        receipt_ref,
        payment,
        items,
        amount,
        now,
        is_split: bool = False,
    ):
        receipt = {
            "table": payment.table,
            "method": payment.method,
            "amount": float(amount),
            "items": [
                self._clean_item(item)
                for item in items
            ],
            "bill_closed": True,
            "payment_type": "split" if is_split else "full",
            "confirmed_by": "admin",
            "created_at": now.isoformat(),
            "date": _day(now),
        }

        transaction.set(receipt_ref, receipt)

        transaction.update(ref, {
            "items": [],
            "paid": True,
            "status": "waiting_payment",
            "updated_at": now.isoformat(),
            "payment_id": receipt_ref.id,
            "payment_amount": float(amount),
            "payment_method": payment.method,
            "shared_paid": 0,
            "shared_item_ids": [],
        })

        return {
            "status": "success",
            "paid": True,
            "payment_id": receipt_ref.id,
        }

    # ---------- เคลียร์โต๊ะ ----------

    def reset_table(
        self,
        table: int,
        opened_at: str,
    ) -> bool:
        """
        เคลียร์เฉพาะโต๊ะที่ชำระครบแล้ว
        เก็บประวัติยอดขายและการชำระเงินไว้
        """
        ref = self.db.collection(self.live_orders).document(
            str(table)
        )

        @transactional
        def reset(transaction):
            snapshot = ref.get(transaction=transaction)

            if not snapshot.exists:
                return False

            data = snapshot.to_dict() or {}

            if data.get("opened_at") != opened_at:
                raise ValueError(TABLE_BILL_CHANGED)

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
        if status not in (
            "cooking",
            "ready",
            "served",
        ):
            raise ValueError("Invalid kitchen status")

        ref = self.db.collection(self.live_orders).document(
            str(table)
        )

        @transactional
        def update(transaction):
            snapshot = ref.get(transaction=transaction)

            if not snapshot.exists:
                return None

            data = snapshot.to_dict() or {}

            if data.get("opened_at") != opened_at:
                raise ValueError(TABLE_BILL_CHANGED)

            items = [
                dict(item)
                for item in data.get("items", [])
            ]

            item = next(
                (
                    row
                    for row in items
                    if row["id"] == item_id
                ),
                None,
            )

            if item is None:
                return None

            if item["qty"] != expected_qty:
                raise ValueError(
                    "Order quantity has changed"
                )

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

    # ---------- ข้อมูล Dashboard ----------

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
            sum(tx["amount"] for tx in today_tx),
            2,
        )

        revenue_yesterday = round(
            sum(tx["amount"] for tx in yesterday_tx),
            2,
        )

        bills_today = sum(
            1
            for tx in today_tx
            if tx.get("bill_closed")
        )

        bills_yesterday = sum(
            1
            for tx in yesterday_tx
            if tx.get("bill_closed")
        )

        top_dishes = self._top_dishes(today, limit=5)
        live = self._live_tables(today_tx)

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
                "active": len(live),
                "total": TableSettingsService().get_count(),
                "live": live,
            },
            "top_dish": (
                top_dishes[0]
                if top_dishes
                else None
            ),
            "top_dishes": top_dishes,
            "recent_transactions": [
                self._public_tx(tx)
                for tx in sorted(
                    today_tx,
                    key=lambda tx: tx["created_at"],
                    reverse=True,
                )[:10]
            ],
            "sales_trend": [
                {
                    "date": day,
                    "total": round(
                        sum(
                            tx["amount"]
                            for tx in tx_by_day.get(day, [])
                        ),
                        2,
                    ),
                }
                for day in day_keys
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

    # ---------- เมนูขายดี ----------

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
            key=lambda row: (
                -row["qty"],
                row["id"],
            ),
        )

        return ranked[:limit]

    # ---------- โต๊ะที่กำลังใช้งาน ----------

    def _live_tables(
        self,
        today_tx: list[dict] | None = None,
    ) -> list[dict]:
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

            if not items and not paid:
                continue

            gross = sum(
                item["price"] * item["qty"]
                for item in items
            )

            shared_paid = float(
                data.get("shared_paid", 0)
            )

            paid_amount = 0.0
            if today_tx and data.get("table") and data.get("opened_at"):
                t_num = data.get("table")
                t_opened = data.get("opened_at")
                paid_amount = round(
                    sum(
                        tx["amount"]
                        for tx in today_tx
                        if tx.get("table") == t_num
                        and tx.get("created_at", "") >= t_opened
                    ),
                    2,
                )

            tables.append({
                "table": data.get("table"),
                "status": data.get("status", "dining"),
                "paid": paid,
                "items": items,
                "total": round(
                    max(0, gross - shared_paid),
                    2,
                ),
                "item_count": sum(
                    item["qty"]
                    for item in items
                ),
                "shared_paid": shared_paid,
                "shared_item_ids": data.get("shared_item_ids", []),
                "paid_amount": paid_amount,
                "opened_at": data.get("opened_at"),
            })

        tables.sort(
            key=lambda table: (
                table["table"] is None,
                table["table"],
            )
        )

        return tables

    # ---------- ยอดขายรายชั่วโมง ----------

    @staticmethod
    def _sales_by_hour(
        today_tx: list[dict],
    ) -> list[dict]:
        totals = [0.0] * 24

        for transaction in today_tx:
            hour = (
                datetime.fromisoformat(
                    transaction["created_at"]
                )
                .astimezone(TH_TZ)
                .hour
            )

            totals[hour] += transaction["amount"]

        return [
            {
                "hour": hour,
                "total": round(value, 2),
            }
            for hour, value in enumerate(totals)
        ]

    @staticmethod
    def _public_tx(transaction: dict) -> dict:
        return {
            "id": transaction["id"],
            "table": transaction.get("table"),
            "method": transaction.get("method"),
            "amount": transaction["amount"],
            "bill_closed": transaction.get(
                "bill_closed",
                False,
            ),
            "payment_type": transaction.get(
                "payment_type"
            ),
            "created_at": transaction["created_at"],
            "item_count": sum(
                item["qty"]
                for item in transaction.get("items", [])
            ),
        }

    @staticmethod
    def _change_pct(
        today: float,
        yesterday: float,
    ) -> float | None:
        if not yesterday:
            return None

        return round(
            (today - yesterday) / yesterday * 100,
            1,
        )