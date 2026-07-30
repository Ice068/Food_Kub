class MenuItem:
    """โมเดลเก็บข้อมูลเมนูอาหาร 1 รายการ

    รูปแบบ data contract ที่ Frontend/User ต้องอ่านตาม
    ฟิลด์ครบ 5 ตัว: id, name, price, image, category
    """

    def __init__(self, id: int, name: str, price: float, image: str, category: str):
        self.id = id
        self.name = name
        self.price = price
        self.image = image
        self.category = category

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "image": self.image,
            "category": self.category,
        }

    @staticmethod
    def from_dict(data: dict) -> "MenuItem":
        return MenuItem(
            id=data["id"],
            name=data["name"],
            price=data["price"],
            image=data["image"],
            category=data["category"],
        )
