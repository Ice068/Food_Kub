from app.models.menu_item import MenuItem
from app.repositories.menu_repository import MenuRepository


class MenuService:
    """จัดการ business logic ของเมนูอาหารทั้งหมด (Create, Read, Update, Delete)
    ไม่ผูกติดกับวิธีการจัดเก็บข้อมูล — รับ repository เข้ามาแทน
    """

    def __init__(self, repository: MenuRepository):
        self._repo = repository

    def get_all(self) -> list[MenuItem]:
        return self._repo.load()

    def get_by_id(self, item_id: int) -> MenuItem | None:
        return next((item for item in self._repo.load() if item.id == item_id), None)

    def add_item(self, name: str, price: float, image: str, category: str) -> MenuItem:
        items = self._repo.load()
        new_id = max((item.id for item in items), default=0) + 1
        new_item = MenuItem(new_id, name, price, image, category)
        items.append(new_item)
        self._repo.save(items)
        return new_item

    def update_item(
        self, item_id: int, name: str, price: float, category: str, image: str | None = None
    ) -> bool:
        items = self._repo.load()
        for item in items:
            if item.id == item_id:
                item.name = name
                item.price = price
                item.category = category
                if image:  # อัปเดตรูปเฉพาะตอนมีการอัปโหลดใหม่จริงๆ
                    item.image = image
                self._repo.save(items)
                return True
        return False

    def delete_item(self, item_id: int) -> bool:
        items = self._repo.load()
        new_items = [item for item in items if item.id != item_id]
        if len(new_items) == len(items):
            return False
        self._repo.save(new_items)
        return True