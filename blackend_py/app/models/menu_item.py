class MenuItem:
    """โมเดลเก็บข้อมูลเมนูอาหาร"""

    def __init__(self, id: int, name: str, price: float, image: str, category: str, available: bool = True):
        self.id = id
        self.name = name
        self.price = price
        self.image = image
        self.category = category
        self.available = available

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "image": self.image,
            "category": self.category,
            "available": self.available
        }
