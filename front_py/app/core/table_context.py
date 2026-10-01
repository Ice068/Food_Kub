from fastapi import Query, Request

MAX_TABLES = 100


def set_table_context(request: Request, table: int | None = Query(None, ge=1, le=MAX_TABLES)):
    """Keep table selection local to each URL, including separate browser tabs."""
    request.state.table_id = table


def table_query(request: Request) -> str:
    table_id = getattr(request.state, "table_id", None)
    return f"?table={table_id}" if table_id is not None else ""
