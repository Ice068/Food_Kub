from app.models.menu_item import MenuItem
from app.core.db import db


class MenuService:
    """จัดการข้อมูลเมนูอาหาร ผ่านฐานข้อมูล Firebase Firestore"""

    def __init__(self):
        self.db = db
        self.collection_name = "menu_items"

    def _seed_default_data_if_empty(self):
        docs = self.db.collection(self.collection_name).limit(1).get(retry=None, timeout=4)
        if len(docs) == 0:
            print("ฐานข้อมูลว่างเปล่า! กำลังเพิ่มข้อมูลเมนูอาหารเริ่มต้น...")
            default_items = [
                {"id": 1, "name": "ผัดไทย", "price": 60.0, "image": "Phat_Thai_kung_Chang_Khien_street_stall.jpg", "category": "จานเดียว"},
                {"id": 2, "name": "ต้มยำกุ้ง", "price": 120.0, "image": "ต้มยำกุ้ง.png", "category": "ต้มแกง"},
                {"id": 3, "name": "ข้าวผัดปู", "price": 80.0, "image": "1382588488-dsc04851-o.jpg", "category": "จานเดียว"},
                {"id": 4, "name": "ส้มตำไทย", "price": 50.0, "image": "1695118621402.jpg", "category": "ยำสลัด"},
                {"id": 5, "name": "แกงเขียวหวานไก่", "price": 90.0, "image": "bafb1ee2-be6b-4293-bf87-eddad7f11fc1.jpg", "category": "ต้มแกง"},
                {"id": 6, "name": "ชาไทยเย็น", "price": 35.0, "image": "ชาไทยไม่ใส่สี-3_0-1024x1024.jpg", "category": "เครื่องดื่ม"},
                {"id": 7, "name": "ผัดกะเพราหมูสับ", "price": 55.0, "image": "pad_kra_pao.jpg", "category": "จานเดียว"},
                {"id": 8, "name": "ข้าวมันไก่", "price": 50.0, "image": "khao_man_gai.jpg", "category": "จานเดียว"},
                {"id": 9, "name": "แกงส้มผักรวม", "price": 70.0, "image": "kaeng_som.jpg", "category": "ต้มแกง"},
                {"id": 10, "name": "ยำวุ้นเส้น", "price": 65.0, "image": "yam_woonsen.jpg", "category": "ยำสลัด"},
                {"id": 11, "name": "น้ำมะนาวโซดา", "price": 30.0, "image": "nam_manao.jpg", "category": "เครื่องดื่ม"},
                {"id": 12, "name": "กล้วยทอด", "price": 40.0, "image": "kluay_tod.jpg", "category": "ของหวาน"},
            ]
            for item in default_items:
                self.db.collection(self.collection_name).document(str(item["id"])).set(item)
            print("เพิ่มข้อมูลเริ่มต้นสำเร็จ!")

    def get_all(self) -> list[MenuItem]:
        # Seed only when the menu is requested, so importing the API does not
        # block backend startup on a Firestore network request.
        self._seed_default_data_if_empty()
        docs = self.db.collection(self.collection_name).stream(retry=None, timeout=4)
        items = []
        for doc in docs:
            data = doc.to_dict()
            items.append(MenuItem(
                id=int(data.get("id")),
                name=str(data.get("name")),
                price=float(data.get("price")),
                image=str(data.get("image")),
                category=str(data.get("category")),
                available=bool(data.get("available", True)),
            ))
        items.sort(key=lambda x: x.id)
        return items

    def get_by_category(self, category: str) -> list[MenuItem]:
        docs = self.db.collection(self.collection_name).where("category", "==", category).stream(retry=None, timeout=4)
        items = []
        for doc in docs:
            data = doc.to_dict()
            items.append(MenuItem(
                id=int(data.get("id")),
                name=str(data.get("name")),
                price=float(data.get("price")),
                image=str(data.get("image")),
                category=str(data.get("category")),
                available=bool(data.get("available", True)),
            ))
        items.sort(key=lambda x: x.id)
        return items

    def get_by_id(self, item_id: int) -> MenuItem | None:
        doc_ref = self.db.collection(self.collection_name).document(str(item_id))
        doc = doc_ref.get(retry=None, timeout=4)
        if doc.exists:
            data = doc.to_dict()
            return MenuItem(
                id=int(data.get("id")),
                name=str(data.get("name")),
                price=float(data.get("price")),
                image=str(data.get("image")),
                category=str(data.get("category")),
                available=bool(data.get("available", True)),
            )
        return None

    def get_categories(self) -> list[str]:
        items = self.get_all()
        seen = []
        for item in items:
            if item.category not in seen:
                seen.append(item.category)
        return seen

    def add_item(self, name: str, price: float, image: str, category: str) -> MenuItem:
        items = self.get_all()
        new_id = max((item.id for item in items), default=0) + 1
        new_item = MenuItem(new_id, name, price, image, category)
        self.db.collection(self.collection_name).document(str(new_id)).set(new_item.to_dict())
        return new_item

    def delete_item(self, item_id: int) -> bool:
        doc_ref = self.db.collection(self.collection_name).document(str(item_id))
        if doc_ref.get(retry=None, timeout=4).exists:
            doc_ref.delete()
            return True
        return False

    def set_availability(self, item_id: int, available: bool) -> bool:
        doc_ref = self.db.collection(self.collection_name).document(str(item_id))
        if not doc_ref.get(retry=None, timeout=4).exists:
            return False
        doc_ref.update({"available": available})
        return True
