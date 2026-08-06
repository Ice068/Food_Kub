import json
import pytest
from app.repositories.menu_repository import JsonMenuRepository
from app.models.menu_item import MenuItem


@pytest.fixture
def repo(tmp_path):
    data_file = tmp_path / "menu.json"
    images_dir = tmp_path / "images"
    return JsonMenuRepository(data_file=str(data_file), images_dir=str(images_dir))


class TestEnsureDataFileExists:
    def test_creates_data_file_if_missing(self, tmp_path):
        data_file = tmp_path / "menu.json"
        JsonMenuRepository(data_file=str(data_file), images_dir=str(tmp_path / "images"))
        assert data_file.exists()

    def test_creates_empty_list_in_new_file(self, tmp_path):
        data_file = tmp_path / "menu.json"
        JsonMenuRepository(data_file=str(data_file), images_dir=str(tmp_path / "images"))
        with open(data_file, encoding="utf-8") as f:
            assert json.load(f) == []

    def test_creates_images_dir(self, tmp_path):
        images_dir = tmp_path / "images"
        JsonMenuRepository(data_file=str(tmp_path / "menu.json"), images_dir=str(images_dir))
        assert images_dir.exists()

    def test_does_not_overwrite_existing_data(self, tmp_path):
        data_file = tmp_path / "menu.json"
        data_file.write_text(
            json.dumps([{"id": 1, "name": "ผัดไทย", "price": 60.0,
                         "image": "x.jpg", "category": "จานเดียว"}], ensure_ascii=False),
            encoding="utf-8",
        )
        repo = JsonMenuRepository(data_file=str(data_file), images_dir=str(tmp_path / "images"))
        assert len(repo.load()) == 1


class TestSaveAndLoad:
    def test_load_returns_empty_list_initially(self, repo):
        assert repo.load() == []

    def test_save_then_load_roundtrip(self, repo):
        items = [MenuItem(1, "ผัดไทย", 60.0, "pad_thai.jpg", "อาหารจานเดียว")]
        repo.save(items)

        loaded = repo.load()
        assert len(loaded) == 1
        assert loaded[0].id == 1
        assert loaded[0].name == "ผัดไทย"

    def test_save_overwrites_previous_data(self, repo):
        repo.save([MenuItem(1, "A", 10.0, "a.jpg", "cat")])
        repo.save([MenuItem(2, "B", 20.0, "b.jpg", "cat")])

        loaded = repo.load()
        assert len(loaded) == 1
        assert loaded[0].id == 2