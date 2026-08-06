import json
import os
from typing import Protocol
from app.models.menu_item import MenuItem


class MenuRepository(Protocol):
    """Interface สำหรับจัดเก็บ/อ่านข้อมูลเมนู ไม่ผูกกับ storage ใดๆ โดยเฉพาะ"""

    def load(self) -> list[MenuItem]: ...
    def save(self, items: list[MenuItem]) -> None: ...


class JsonMenuRepository:
    """Implementation ที่เก็บข้อมูลเป็นไฟล์ JSON"""

    def __init__(self, data_file: str, images_dir: str):
        self._data_file = data_file
        self._ensure_data_file_exists(images_dir)

    def _ensure_data_file_exists(self, images_dir: str) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        os.makedirs(images_dir, exist_ok=True)
        if not os.path.exists(self._data_file):
            self.save([])

    def load(self) -> list[MenuItem]:
        with open(self._data_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [MenuItem.from_dict(item) for item in raw]

    def save(self, items: list[MenuItem]) -> None:
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump([item.to_dict() for item in items], f, ensure_ascii=False, indent=2)