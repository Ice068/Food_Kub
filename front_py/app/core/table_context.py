import httpx
from app.core.backend import backend_client

from fastapi import HTTPException, Query, Request

from app.core.config import settings
from app.services.cart_service import CartService


MAX_TABLES = 100


async def set_table_context(
    request: Request,
    table: int | None = Query(
        None,
        ge=1,
        le=MAX_TABLES,
    ),
):
    request.state.table_id = table
    request.state.live_table = None

    if table is None:
        return

    # อ่านบิลล่าสุดจาก Backend
    try:
        async with backend_client(
            timeout=5.0
        ) as client:
            response = await client.get(
                f"{settings.BACKEND_URL}"
                f"/api/stats/live-orders/{table}"
            )

            response.raise_for_status()
            live = response.json()["table"]

            count_response = await client.get(f"{settings.BACKEND_URL}/api/table-settings")
            count_response.raise_for_status()
            table_count = int(count_response.json()["table_count"])

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "ตรวจสอบบิลโต๊ะไม่ได้ "
                "กรุณาตรวจสอบ Backend แล้วลองใหม่"
            ),
        ) from exc

    if table > table_count and not live:
        raise HTTPException(404, "ไม่พบโต๊ะนี้ในร้าน กรุณาสแกน QR ประจำโต๊ะอีกครั้ง")

    request.state.live_table = live

    # แยกข้อมูลลูกค้าตามรอบบิล
    generation_key = f"bill_generation_{table}"
    generation = live.get("opened_at") if live else None
    previous = request.session.get(generation_key)

    if (
        (previous and previous != generation)
        or (live and live.get("paid"))
    ):
        request.session[f"cart_table_{table}"] = {}

    if generation and request.session.get(f"cart_table_{table}"):
        request.session[generation_key] = generation
    else:
        request.session.pop(generation_key, None)

    # Backend owns submitted orders. Do not duplicate large live bills in the
    # signed browser cookie; only each customer's unsubmitted cart belongs there.
    for key in list(request.session):
        if key.startswith(("order_table_", "orders_table_", "shared_paid_table_", "shared_items_table_")):
            request.session.pop(key, None)
        elif key.startswith("bill_generation_") and not request.session.get("cart_table_" + key.removeprefix("bill_generation_")):
            request.session.pop(key, None)

    # ใช้รายการในบิลที่ Backend เก็บไว้
    live_dict = live or {}
    backend_shared_ids = {
        int(x) for x in live_dict.get("shared_item_ids", [])
    }
    existing_state = CartService.TABLE_STATE.get(str(table), {})
    preserved_shared_ids = (
        backend_shared_ids
        or (
            set(existing_state.get("shared_item_ids", []))
            or set(request.session.get(f"{CartService.SHARED_ITEMS_KEY}_table_{table}", []))
            if live and previous == generation and not live.get("paid")
            else set()
        )
    )

    CartService.TABLE_STATE[str(table)] = {
        "orders": {
            str(item["id"]): item["qty"]
            for item in (live_dict.get("items", []) if not live_dict.get("paid") else [])
        },
        "shared_paid": float(
            live_dict.get("shared_paid", 0) if not live_dict.get("paid") else 0
        ),
        "shared_item_ids": preserved_shared_ids if not live_dict.get("paid") else set(),
    }

    # ป้องกันแก้ตะกร้าระหว่างเก็บเงินหรือหลังจ่ายครบ
    if (
        request.method == "POST"
        and request.url.path.startswith("/cart/")
        and live
        and (
            live.get("paid")
            or live.get("status") == "waiting_payment"
        )
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "โต๊ะนี้รอชำระหรือชำระแล้ว "
                "กรุณาติดต่อพนักงาน"
            ),
        )


def table_query(request: Request) -> str:
    table_id = getattr(
        request.state,
        "table_id",
        None,
    )

    return (
        f"?table={table_id}"
        if table_id is not None
        else ""
    )
