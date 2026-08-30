class MenuItem:
    """โมเดลเก็บข้อมูลเมนูอาหาร"""

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
            "category": self.category
        }
