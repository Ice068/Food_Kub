from app.models.menu_item import MenuItem


class MenuService:
    """จัดการข้อมูลเมนูอาหาร (mock data)
    ถ้าในอนาคตต้องต่อฐานข้อมูลจริง ให้แก้ logic ในคลาสนี้ที่เดียว
    """

    def __init__(self):
        self._menu_items: list[MenuItem] = [
            MenuItem(1, "ผัดไทย", 60, "Phat_Thai_kung_Chang_Khien_street_stall.jpg", "จานเดียว"),
            MenuItem(2, "ต้มยำกุ้ง", 120, "ต้มยำกุ้ง.png", "ต้มแกง"),
            MenuItem(3, "ข้าวผัดปู", 80, "1382588488-dsc04851-o.jpg", "จานเดียว"),
            MenuItem(4, "ส้มตำไทย", 50, "1695118621402.jpg", "ยำสลัด"),
            MenuItem(5, "แกงเขียวหวานไก่", 90, "bafb1ee2-be6b-4293-bf87-eddad7f11fc1.jpg", "ต้มแกง"),
            MenuItem(6, "ชาไทยเย็น", 35, "ชาไทยไม่ใส่สี-3_0-1024x1024.jpg", "เครื่องดื่ม"),
            MenuItem(7, "ผัดกะเพราหมูสับ", 55, "pad_kra_pao.jpg", "จานเดียว"),
            MenuItem(8, "ข้าวมันไก่", 50, "khao_man_gai.jpg", "จานเดียว"),
            MenuItem(9, "แกงส้มผักรวม", 70, "kaeng_som.jpg", "ต้มแกง"),
            MenuItem(10, "ยำวุ้นเส้น", 65, "yam_woonsen.jpg", "ยำสลัด"),
            MenuItem(11, "น้ำมะนาวโซดา", 30, "nam_manao.jpg", "เครื่องดื่ม"),
            MenuItem(12, "กล้วยทอด", 40, "kluay_tod.jpg", "ของหวาน"),
        ]

    def get_all(self) -> list[MenuItem]:
        return self._menu_items

    def get_by_category(self, category: str) -> list[MenuItem]:
        return [item for item in self._menu_items if item.category == category]

    def get_by_id(self, item_id: int) -> MenuItem | None:
        return next((item for item in self._menu_items if item.id == item_id), None)

    def get_categories(self) -> list[str]:
        # เอาหมวดหมู่ทั้งหมดแบบไม่ซ้ำ คงลำดับการเจอครั้งแรก
        seen = []
        for item in self._menu_items:
            if item.category not in seen:
                seen.append(item.category)
        return seen

    # ---------- ส่วนที่เพิ่มใหม่สำหรับ Admin ----------
    def add_item(self, name: str, price: float, image: str, category: str) -> MenuItem:
        """เพิ่มเมนูใหม่ id จะรันต่อจากตัวสูงสุดที่มีอยู่อัตโนมัติ"""
        new_id = max((item.id for item in self._menu_items), default=0) + 1
        new_item = MenuItem(new_id, name, price, image, category)
        self._menu_items.append(new_item)
        return new_item

    def delete_item(self, item_id: int) -> bool:
        """ลบเมนู คืนค่า True ถ้าลบสำเร็จ"""
        item = self.get_by_id(item_id)
        if item:
            self._menu_items.remove(item)
            return True
        return False