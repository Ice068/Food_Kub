import pytest
from app.services.menu_service import MenuService
from app.models.menu_item import MenuItem


class FakeMenuRepository:
    """Fake repository เก็บข้อมูลใน memory แทนไฟล์จริง ใช้สำหรับเทสเท่านั้น"""

    def __init__(self, initial_items=None):
        self._items = initial_items or []

    def load(self) -> list[MenuItem]:
        return list(self._items)

    def save(self, items: list[MenuItem]) -> None:
        self._items = list(items)


@pytest.fixture
def empty_service():
    return MenuService(FakeMenuRepository())


@pytest.fixture
def service_with_items():
    items = [
        MenuItem(1, "ผัดไทย", 60.0, "pad_thai.jpg", "อาหารจานเดียว"),
        MenuItem(2, "ต้มยำกุ้ง", 120.0, "tomyum.jpg", "อาหารจานเดียว"),
    ]
    return MenuService(FakeMenuRepository(items))


class TestGetAll:
    def test_returns_empty_list_when_no_items(self, empty_service):
        assert empty_service.get_all() == []

    def test_returns_all_items(self, service_with_items):
        items = service_with_items.get_all()
        assert len(items) == 2


class TestGetById:
    def test_returns_item_when_found(self, service_with_items):
        item = service_with_items.get_by_id(1)
        assert item is not None
        assert item.name == "ผัดไทย"

    def test_returns_none_when_not_found(self, service_with_items):
        item = service_with_items.get_by_id(999)
        assert item is None


class TestAddItem:
    def test_assigns_id_1_when_empty(self, empty_service):
        item = empty_service.add_item("ส้มตำ", 50.0, "somtam.jpg", "อาหารเผ็ด")
        assert item.id == 1

    def test_increments_id_from_max(self, service_with_items):
        item = service_with_items.add_item("แกงเขียวหวาน", 80.0, "curry.jpg", "แกง")
        assert item.id == 3

    def test_new_item_is_persisted(self, empty_service):
        empty_service.add_item("ส้มตำ", 50.0, "somtam.jpg", "อาหารเผ็ด")
        assert len(empty_service.get_all()) == 1


class TestUpdateItem:
    def test_updates_existing_item(self, service_with_items):
        result = service_with_items.update_item(1, "ผัดไทยกุ้งสด", 70.0, "อาหารจานเดียว")
        assert result is True
        item = service_with_items.get_by_id(1)
        assert item.name == "ผัดไทยกุ้งสด"
        assert item.price == 70.0

    def test_returns_false_when_item_not_found(self, service_with_items):
        result = service_with_items.update_item(999, "ไม่มีจริง", 0.0, "-")
        assert result is False

    def test_keeps_old_image_when_no_new_image_given(self, service_with_items):
        service_with_items.update_item(1, "ผัดไทยกุ้งสด", 70.0, "อาหารจานเดียว", image=None)
        item = service_with_items.get_by_id(1)
        assert item.image == "pad_thai.jpg"

    def test_replaces_image_when_new_image_given(self, service_with_items):
        service_with_items.update_item(1, "ผัดไทยกุ้งสด", 70.0, "อาหารจานเดียว", image="new.jpg")
        item = service_with_items.get_by_id(1)
        assert item.image == "new.jpg"


class TestDeleteItem:
    def test_deletes_existing_item(self, service_with_items):
        result = service_with_items.delete_item(1)
        assert result is True
        assert service_with_items.get_by_id(1) is None

    def test_returns_false_when_item_not_found(self, service_with_items):
        result = service_with_items.delete_item(999)
        assert result is False

    def test_does_not_affect_other_items(self, service_with_items):
        service_with_items.delete_item(1)
        assert service_with_items.get_by_id(2) is not None