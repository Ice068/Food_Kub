import httpx
from app.core.backend import backend_client

from app.core.config import settings
from app.core.admin_auth import admin_api_key


class TableSettingsService:
    """อ่านและบันทึกจำนวนโต๊ะผ่าน Backend"""

    def __init__(self):
        self.url = (
            f"{settings.BACKEND_URL.rstrip('/')}"
            "/api/table-settings"
        )

    async def get_count(self) -> int:
        """อ่านจำนวนโต๊ะที่บันทึกไว้"""
        async with backend_client(timeout=10.0) as client:
            response = await client.get(self.url)
            response.raise_for_status()

            return response.json()["table_count"]

    async def set_count(self, count: int) -> None:
        """บันทึกจำนวนโต๊ะ และส่ง HTTP error ให้ Router จัดการ"""
        async with backend_client(timeout=10.0) as client:
            response = await client.put(
                self.url,
                headers={"X-Food-Kub-Key": admin_api_key()},
                json={
                    "table_count": count,
                },
            )
            response.raise_for_status()
