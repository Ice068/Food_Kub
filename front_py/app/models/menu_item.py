class MenuItem:
    """โมเดลเก็บข้อมูลเมนูอาหาร"""

    def __init__(self, id: int, name: str, price: float, image: str, category: str, **kwargs):
        self.id = id
        self.name = name
        self.price = price
        self.image = image
        self.category = category

    @property
    def image_url(self) -> str:
        if not self.image:
            return "https://placehold.co/300x200?text=No+Image"
        if self.image.startswith("http://") or self.image.startswith("https://"):
            return self.image
        if self.image.startswith("/"):
            return self.image
        return f"/static/images/{self.image}"

    def to_dict(self) -> dict:
        """แปลงข้อมูลเมนูอาหารเป็น dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "image": self.image,
            "image_url": self.image_url,
            "category": self.category
        }