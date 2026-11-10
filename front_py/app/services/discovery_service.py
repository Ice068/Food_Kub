import random
from urllib.parse import quote, urlsplit


# เปลี่ยนเป็น ID อาหารที่อยากแนะนำ เรียงตามลำดับที่อยากแสดง
RECOMMENDED_IDS = (1, 3, 7)

MAX_WHEEL_ITEMS = 12

WHEEL_COLORS = (
    "#d9480f",
    "#ffd8a8",
    "#2b8a3e",
    "#d3f9d8",
    "#e67700",
    "#fff3bf",
)


class DiscoveryService:
    @staticmethod
    def image_url(value: str) -> str:
        """รองรับทั้งลิงก์รูปออนไลน์และชื่อไฟล์ใน static/images"""
        value = (value or "").strip()

        if not value:
            return ""

        parsed = urlsplit(value)

        if parsed.scheme in ("http", "https") and parsed.netloc:
            return value

        if (
            parsed.scheme
            or parsed.netloc
            or "\\" in value
            or ".." in value.split("/")
        ):
            return ""

        if value.startswith("/static/"):
            return value

        if value.startswith("/"):
            return ""

        return "/static/images/" + quote(value, safe="/")

    def prepare_items(self, menu_items):
        items = []

        for menu_item in menu_items:
            item = menu_item.to_dict()
            item["image_url"] = self.image_url(item["image"])
            items.append(item)

        return items

    @staticmethod
    def recommendations(items):
        by_id = {item["id"]: item for item in items}

        return [
            by_id[item_id]
            for item_id in RECOMMENDED_IDS
            if item_id in by_id
        ]

    @staticmethod
    def build_wheel(items, spin=False, rng=None):
        rng = rng or random.SystemRandom()

        # ถ้ามีเกิน 12 เมนู สุ่มเข้าวงล้อครั้งละ 12 เมนู
        if spin and len(items) > MAX_WHEEL_ITEMS:
            wheel = rng.sample(items, MAX_WHEEL_ITEMS)
        else:
            wheel = list(items[:MAX_WHEEL_ITEMS])

        count = len(wheel)
        index = rng.randrange(count) if spin and count else None
        step = 360 / count if count else 360

        segments = []
        stops = []

        for number, item in enumerate(wheel):
            color = WHEEL_COLORS[number % len(WHEEL_COLORS)]

            segments.append({
                "number": number + 1,
                "angle": (number + 0.5) * step,
                "item": item,
            })

            stops.append(
                f"{color} "
                f"{number * step:.8f}deg "
                f"{(number + 1) * step:.8f}deg"
            )

        # ลูกศรอยู่ด้านบน หมุนให้กลางช่องที่ชนะมาตรงลูกศร
        rotation = (
            1800 + (360 - (index + 0.5) * step)
            if index is not None
            else 0
        )

        return {
            "wheel_items": wheel,
            "segments": segments,
            "gradient": (
                "conic-gradient(" + ", ".join(stops) + ")"
                if stops
                else "#eee"
            ),
            "winner": wheel[index] if index is not None else None,
            "winner_index": index,
            "rotation": rotation,
            "pool_count": len(items),
        }