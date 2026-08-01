import json
import os

from app.core import settings
from app.models.menu_item import MenuItem


class MenuService:
    """จัดการข้อมูลเมนูอาหารทั้งหมด (Create, Read, Update, Delete)
    เก็บข้อมูลเป็นไฟล์ JSON ที่ settings.MENU_DATA_FILE
    """

    def __init__(self):
        self._ensure_data_file_exists()

    def _ensure_data_file_exists(self):
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        os.makedirs(settings.MENU_IMAGES_DIR, exist_ok=True)
        if not os.path.exists(settings.MENU_DATA_FILE):
            with open(settings.MENU_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load(self) -> list[MenuItem]:
        with open(settings.MENU_DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [MenuItem.from_dict(item) for item in raw]

    def _save(self, items: list[MenuItem]):
        with open(settings.MENU_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([item.to_dict() for item in items], f, ensure_ascii=False, indent=2)

    def get_all(self) -> list[MenuItem]:
        return self._load()

    def get_by_id(self, item_id: int) -> MenuItem | None:
        return next((item for item in self._load() if item.id == item_id), None)

    def add_item(self, name: str, price: float, image: str, category: str) -> MenuItem:
        items = self._load()
        new_id = max((item.id for item in items), default=0) + 1
        new_item = MenuItem(new_id, name, price, image, category)
        items.append(new_item)
        self._save(items)
        return new_item

    def update_item(
        self, item_id: int, name: str, price: float, category: str, image: str | None = None
    ) -> bool:
        items = self._load()
        for item in items:
            if item.id == item_id:
                item.name = name
                item.price = price
                item.category = category
                if image:  # อัปเดตรูปเฉพาะตอนมีการอัปโหลดใหม่จริงๆ
                    item.image = image
                self._save(items)
                return True
        return False

    def delete_item(self, item_id: int) -> bool:
        items = self._load()
        new_items = [item for item in items if item.id != item_id]
        if len(new_items) == len(items):
            return False
        self._save(new_items)
        return True
