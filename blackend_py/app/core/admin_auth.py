import os
import secrets
from pathlib import Path


def admin_api_key(create: bool = False) -> str:
    configured = os.environ.get("FOOD_KUB_ADMIN_API_KEY")
    if configured:
        return configured

    # ไฟล์กุญแจที่ root ของโปรเจกต์ Food_Kub
    path = Path(__file__).resolve().parents[3] / ".food_kub_admin_key"

    if create:
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass

    return path.read_text(encoding="utf-8").strip()