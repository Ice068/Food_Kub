import httpx
from app.core.backend import backend_client
from app.models.menu_item import MenuItem
from app.core.admin_auth import admin_api_key
from app.core.config import settings


class MenuService:
    """ดึงข้อมูลเมนูอาหารจากเซิร์ฟเวอร์ Backend (blackend_py) ผ่าน API"""

    def __init__(self):
        self.backend_url = settings.BACKEND_URL

    async def get_all(self) -> list[MenuItem]:
        async with backend_client() as client:
            resp = await client.get(f"{self.backend_url}/api/menu")
            resp.raise_for_status()
            data = resp.json()
            return [MenuItem(**item) for item in data]

    async def get_by_category(self, category: str) -> list[MenuItem]:
        async with backend_client() as client:
            resp = await client.get(f"{self.backend_url}/api/menu/category/{category}")
            resp.raise_for_status()
            data = resp.json()
            return [MenuItem(**item) for item in data]

    async def get_by_id(self, item_id: int) -> MenuItem | None:
        async with backend_client() as client:
            resp = await client.get(f"{self.backend_url}/api/menu/{item_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return MenuItem(**data)

    async def get_categories(self) -> list[str]:
        async with backend_client() as client:
            resp = await client.get(f"{self.backend_url}/api/menu/categories")
            resp.raise_for_status()
            return resp.json()

    async def add_item(self, name: str, price: float, image: str, category: str) -> MenuItem:
        async with backend_client() as client:
            payload = {
                "name": name,
                "price": price,
                "image": image,
                "category": category
            }
            resp = await client.post(f"{self.backend_url}/api/admin/add", json=payload, headers={"X-Food-Kub-Key": admin_api_key()})
            resp.raise_for_status()
            result = resp.json()
            return MenuItem(**result["item"])

    async def delete_item(self, item_id: int) -> bool:
        async with backend_client() as client:
            resp = await client.post(f"{self.backend_url}/api/admin/delete/{item_id}", headers={"X-Food-Kub-Key": admin_api_key()})
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            return True
    async def update_item(self, item_id: int, name: str, price: float, image: str, category: str) -> MenuItem:
        async with backend_client() as client:
            response = await client.post(f"{self.backend_url}/api/admin/edit/{item_id}",
                json={"name": name, "price": price, "image": image, "category": category},
                headers={"X-Food-Kub-Key": admin_api_key()})
            response.raise_for_status()
            return MenuItem(**response.json()["item"])
