import httpx

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
        async with httpx.AsyncClient(
            timeout=5.0
        ) as client:
            response = await client.get(
                f"{settings.BACKEND_URL}"
                f"/api/stats/live-orders/{table}"
            )

            response.raise_for_status()
            live = response.json()["table"]

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

    if generation:
        request.session[generation_key] = generation
    else:
        request.session.pop(generation_key, None)

    # ใช้รายการในบิลที่ Backend เก็บไว้
    CartService.TABLE_STATE[str(table)] = {
        "orders": {
            str(item["id"]): item["qty"]
            for item in (live or {}).get("items", [])
        },
        "shared_paid": float(
            (live or {}).get("shared_paid", 0)
        ),
        "shared_item_ids": set(),
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