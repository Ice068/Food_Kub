import os


class Settings:
    r"""เก็บค่า config รวมศูนย์ของAdmin (ตอนนี้ยังไม่ผูกกับ User app)

    ตำแหน่งไฟล์ข้อมูล (MENU_DATA_DIR) ตั้งค่าผ่าน environment variable ได้
    ถ้าไม่ตั้งจะใช้โฟลเดอร์ data/ ที่อยู่ในโปรเจกต์นี้เป็นค่าเริ่มต้น

    จะใช้ path ไหนร่วมกัน
    แล้วตั้ง environment variable MENU_DATA_DIR ให้ทั้งสองฝั่งชี้ไปที่เดียวกัน เช่น:
        set MENU_DATA_DIR=D:\shared_data      (Windows)
        export MENU_DATA_DIR=/srv/shared_data  (Mac/Linux)
    """
    APP_TITLE: str = "Admin - จัดการเมนู"
    TEMPLATES_DIR: str = "templates"
    STATIC_DIR: str = "static"
    STATIC_URL: str = "/static"

    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../admin_pyt

    # ถ้ามี env var MENU_DATA_DIR ให้ใช้ค่านั้น ไม่งั้น fallback เป็น ./data ในโปรเจกต์นี้เอง
    DATA_DIR = os.environ.get("MENU_DATA_DIR", os.path.join(APP_DIR, "data"))

    MENU_DATA_FILE = os.path.join(DATA_DIR, "menu.json")
    MENU_IMAGES_DIR = os.path.join(DATA_DIR, "images")


settings = Settings()