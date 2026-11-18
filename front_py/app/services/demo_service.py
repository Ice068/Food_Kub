"""Durable, isolated demonstration API. Enabled only with FOOD_KUB_DEMO=1.

One SQLite transaction owns each mutation, including bill version checks. Sample
payments are explicitly labelled simulations and never generate a bank QR code.
"""
import json
import sqlite3
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone

import httpx
from app.core.config import settings

TH_TZ = timezone(timedelta(hours=7))

SEED_MENU = [
    (1, "ผัดไทยกุ้งสด", 85, "Phat_Thai_kung_Chang_Khien_street_stall.jpg", "จานเดียว"),
    (2, "ต้มยำกุ้งน้ำข้น", 145, "ต้มยำกุ้ง.png", "ต้มแกง"),
    (3, "ข้าวผัดปู", 95, "1382588488-dsc04851-o.jpg", "จานเดียว"),
    (4, "ส้มตำไทย", 65, "1695118621402.jpg", "ยำสลัด"),
    (5, "แกงเขียวหวานไก่", 95, "bafb1ee2-be6b-4293-bf87-eddad7f11fc1.jpg", "ต้มแกง"),
    (6, "ชาไทยเย็น", 45, "ชาไทยไม่ใส่สี-3_0-1024x1024.jpg", "เครื่องดื่ม"),
    (7, "ผัดกะเพราหมูสับ", 75, "pad_kra_pao.jpg", "จานเดียว"),
    (8, "ข้าวมันไก่", 65, "khao_man_gai.jpg", "จานเดียว"),
    (9, "แกงส้มผักรวม", 95, "kaeng_som.jpg", "ต้มแกง"),
    (10, "ยำวุ้นเส้น", 85, "yam_woonsen.jpg", "ยำสลัด"),
    (11, "น้ำมะนาวโซดา", 40, "nam_manao.jpg", "เครื่องดื่ม"),
    (12, "กล้วยทอด", 55, "kluay_tod.jpg", "ของหวาน"),
]


def _now():
    return datetime.now(TH_TZ)


def _initial_state():
    menu = [{"id": i, "name": n, "price": p, "image": img,
             "category": cat, "available": True} for i, n, p, img, cat in SEED_MENU]
    return {"menu": menu, "next_id": 13, "table_count": 10,
            "live": {}, "orders": [], "transactions": []}


class DemoError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail


def _error(status, message):
    raise DemoError(status, message)


def _total(items):
    return round(sum(float(i["price"]) * int(i["qty"]) for i in items), 2)


def _public_table(live):
    if not live:
        return None
    # Match production: the live table contains only unpaid items; history lives
    # in transactions. Normalize older persisted demo records on reads as well.
    paid = bool(live.get("paid"))
    items = [] if paid else live["items"]
    return {**live, "items": items,
            "total": 0 if paid else max(0, round(_total(items) - live.get("shared_paid", 0), 2)),
            "item_count": sum(i["qty"] for i in items),
            "shared_paid": 0 if paid else live.get("shared_paid", 0),
            "shared_item_ids": [] if paid else live.get("shared_item_ids", []),
            "paid_amount": live.get("paid_amount", 0)}


def _fingerprint(items):
    return sorted((int(i["id"]), float(i["price"]), int(i["qty"])) for i in items)


def _dashboard(state):
    now = _now()
    today, yesterday = now.date().isoformat(), (now - timedelta(days=1)).date().isoformat()
    txs = state["transactions"]
    today_tx = [t for t in txs if t["date"] == today]
    yesterday_tx = [t for t in txs if t["date"] == yesterday]
    def metric(field):
        a = sum(t[field] for t in today_tx)
        b = sum(t[field] for t in yesterday_tx)
        return {"today": round(a, 2), "yesterday": round(b, 2),
                "change_pct": round((a-b)/b*100, 1) if b else None}
    counts = {}
    for order in state["orders"]:
        if order["date"] != today:
            continue
        for item in order["items"]:
            row = counts.setdefault(item["id"], {"id": item["id"], "name": item["name"], "qty": 0})
            row["qty"] += item["qty"]
    top = sorted(counts.values(), key=lambda r: (-r["qty"], r["id"]))[:5]
    live = [{**_public_table(t), "paid_amount": round(sum(
                tx["amount"] for tx in txs if tx.get("table") == t["table"]
                and tx["created_at"] >= t["opened_at"]), 2)}
            for t in state["live"].values()]
    daily, hourly = defaultdict(float), defaultdict(float)
    for tx in txs:
        daily[tx["date"]] += tx["amount"]
    for tx in today_tx:
        hourly[datetime.fromisoformat(tx["created_at"]).hour] += tx["amount"]
    return {
        "generated_at": now.isoformat(), "revenue": metric("amount"), "bills": metric("bill_closed"),
        "tables": {"active": len(live), "total": state["table_count"], "live": live},
        "top_dish": top[0] if top else None, "top_dishes": top,
        "recent_transactions": [{**t, "item_count": sum(i["qty"] for i in t["items"])}
                                for t in sorted(today_tx, key=lambda t: t["created_at"], reverse=True)[:10]],
        "sales_trend": [{"date": (now-timedelta(days=d)).date().isoformat(),
                         "total": round(daily[(now-timedelta(days=d)).date().isoformat()], 2)}
                        for d in range(6, -1, -1)],
        "sales_by_hour": [{"hour": h, "total": round(hourly[h], 2)} for h in range(24)],
    }


def _event(state, kind, payload):
    now = _now()
    event = {**payload, "id": f"demo-{uuid.uuid4().hex[:12]}",
             "created_at": now.isoformat(), "date": now.date().isoformat()}
    state[kind].append(event)
    return event


def _dispatch(state, method, path, payload):
    if path == "/api/menu" and method == "GET":
        return state["menu"]
    if path == "/api/menu/categories":
        return list(dict.fromkeys(i["category"] for i in state["menu"]))
    if path.startswith("/api/menu/category/"):
        return [i for i in state["menu"] if i["category"] == path.rsplit("/", 1)[1]]
    if path.startswith("/api/menu/"):
        item = next((i for i in state["menu"] if str(i["id"]) == path.rsplit("/", 1)[1]), None)
        return item or _error(404, "ไม่พบเมนูนี้")
    if path == "/api/admin/add":
        item = {**payload, "id": state["next_id"], "available": True}
        state["next_id"] += 1
        state["menu"].append(item)
        return {"status": "success", "item": item}
    if path.startswith(("/api/admin/edit/", "/api/admin/delete/", "/api/stats/availability/")):
        item_id = int(path.rsplit("/", 1)[1])
        item = next((i for i in state["menu"] if i["id"] == item_id), None)
        if not item:
            _error(404, "ไม่พบเมนูนี้")
        if "/delete/" in path:
            if any(any(i["id"] == item_id for i in t["items"]) and not t.get("paid") for t in state["live"].values()):
                _error(409, "เมนูนี้อยู่ในบิลที่ยังไม่ชำระ ปิดขายแทนการลบได้")
            state["menu"].remove(item)
        else:
            item.update({k: v for k, v in payload.items() if k in ("name", "price", "category", "image", "available")})
        return {"status": "success", "item": item}
    if path == "/api/table-settings":
        if method == "PUT":
            count = payload.get("table_count")
            if type(count) is not int or not 1 <= count <= 100:
                _error(422, "จำนวนโต๊ะต้องอยู่ระหว่าง 1–100")
            state["table_count"] = count
        return {"table_count": state["table_count"]}
    if path == "/api/payment/methods":
        return [{"id": "cash", "name": "ทดลองชำระเงิน · ไม่มีการเก็บเงินจริง"}]
    if path == "/api/payment/process":
        if payload.get("method") != "cash":
            _error(400, "โหมดทดลองรองรับการชำระจำลองเท่านั้น")
        return {"status": "success", "payment_id": f"demo-{uuid.uuid4().hex}",
                "method": "cash", "method_name": "ชำระเงินจำลอง", "amount": payload["amount"],
                "message": "รายการทดลองสำเร็จ ไม่มีการเก็บเงินจริง", "demo": True}
    if path == "/api/stats/orders":
        return _event(state, "orders", payload)
    if path == "/api/stats/transactions":
        return _event(state, "transactions", payload)
    if path == "/api/stats/dashboard":
        return _dashboard(state)
    prefix = "/api/stats/live-orders/"
    if not path.startswith(prefix):
        _error(404, "ไม่พบรายการที่ขอ")
    parts = path[len(prefix):].split("/")
    tid = str(int(parts[0]))
    live = state["live"].get(tid)
    action = parts[1] if len(parts) > 1 else ""
    if method == "GET":
        return {"table": _public_table(live)}
    if method == "PUT" and not action:
        previous = live or {}
        if previous.get("paid"):
            _error(409, "โต๊ะชำระแล้ว กรุณาเคลียร์โต๊ะก่อน")
        if previous and payload.get("expected_opened_at") != previous["opened_at"]:
            _error(409, "รอบบิลเปลี่ยน กรุณาโหลดใหม่")
        if payload.get("expected_updated_at") and payload["expected_updated_at"] != previous.get("updated_at"):
            _error(409, "บิลเปลี่ยน กรุณาโหลดใหม่")
        if previous.get("status") == "waiting_payment" and payload.get("status") == "dining":
            _error(409, "โต๊ะกำลังรอชำระ")
        old = {i["id"]: i for i in previous.get("items", [])}
        items = [{**i, "kitchen_status": old.get(i["id"], {}).get("kitchen_status", "cooking")
                  if old.get(i["id"], {}).get("qty") == i["qty"] else "cooking"} for i in payload["items"]]
        stamp = _now().isoformat()
        state["live"][tid] = {"table": int(tid), "items": items, "paid": False,
                              "status": payload.get("status") or previous.get("status", "dining"),
                              "shared_paid": payload.get("shared_paid", 0),
                              "shared_item_ids": payload.get("shared_item_ids", previous.get("shared_item_ids", [])),
                              "opened_at": previous.get("opened_at") or stamp, "updated_at": stamp}
        return {"status": "success", "table": _public_table(state["live"][tid])}
    if not live:
        _error(404, "ไม่พบบิลโต๊ะนี้")
    if action == "paid":
        last = next((tx for tx in reversed(state["transactions"]) if tx.get("table") == int(tid)), {})
        paid_amount = sum(tx["amount"] for tx in state["transactions"]
                          if tx.get("table") == int(tid) and tx["created_at"] >= live["opened_at"])
        live.update(paid=True, status="waiting_payment", items=[], updated_at=_now().isoformat(),
                    shared_paid=0, shared_item_ids=[], payment_amount=last.get("amount", 0),
                    payment_method=last.get("method", "cash"), paid_amount=round(paid_amount, 2))
        return {"status": "success", "table": _public_table(live)}
    if payload.get("opened_at") != live["opened_at"]:
        _error(409, "รอบบิลเปลี่ยน กรุณาโหลดใหม่")
    if action == "reset":
        if not live.get("paid"):
            _error(409, "ต้องชำระบิลก่อนเคลียร์โต๊ะ")
        del state["live"][tid]
        return {"status": "success"}
    if action == "items" and len(parts) == 4:
        item = next((i for i in live["items"] if i["id"] == int(parts[2])), None)
        if not item:
            _error(404, "ไม่พบรายการอาหาร")
        if live.get("paid") or item["qty"] != payload["expected_qty"]:
            _error(409, "รายการเปลี่ยน กรุณาโหลดใหม่")
        item["kitchen_status"] = payload["status"]
        live["updated_at"] = _now().isoformat()
        return {"status": "success", "item": item}
    if action in ("request-payment", "confirm-payment"):
        if live.get("paid"):
            _error(409, "บิลนี้ชำระแล้ว")
        if _fingerprint(payload["items"]) != _fingerprint(live["items"]):
            _error(409, "รายการในบิลเปลี่ยนแล้ว")
        amount = _public_table(live)["total"]
        if round(float(payload.get("expected_total", -1)), 2) != amount:
            _error(409, "ยอดเงินเปลี่ยนแล้ว")
        if action == "request-payment":
            live["status"] = "waiting_payment"
        else:
            _event(state, "transactions", {"table": int(tid), "method": payload["method"],
                    "amount": amount, "items": live["items"], "bill_closed": True, "payment_type": "full"})
            paid_amount = sum(tx["amount"] for tx in state["transactions"]
                              if tx.get("table") == int(tid) and tx["created_at"] >= live["opened_at"])
            live.update(paid=True, status="waiting_payment", items=[], shared_paid=0, shared_item_ids=[],
                        paid_amount=round(paid_amount, 2), payment_amount=amount, payment_method=payload["method"])
        live["updated_at"] = _now().isoformat()
        return {"status": "success", "table": _public_table(live)}
    _error(404, "ไม่พบคำสั่งนี้")


def demo_request(request: httpx.Request) -> httpx.Response:
    """httpx transport handler with an atomic, process-safe durable state update."""
    settings.DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(request.content) if request.content else {}
        with closing(sqlite3.connect(settings.DEMO_DB, timeout=10)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS demo_state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT data FROM demo_state WHERE id=1").fetchone()
            state = json.loads(row[0]) if row else _initial_state()
            result = _dispatch(state, request.method, request.url.path, payload)
            connection.execute("INSERT OR REPLACE INTO demo_state VALUES (1, ?)", (json.dumps(state, ensure_ascii=False),))
        return httpx.Response(200, json=result)
    except DemoError as exc:
        return httpx.Response(exc.status, json={"detail": exc.detail})
    except (ValueError, KeyError, TypeError):
        return httpx.Response(422, json={"detail": "ข้อมูลไม่ถูกต้อง"})
