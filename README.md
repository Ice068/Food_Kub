# หัวข้อ : ระบบสั่งอาหาร
## สั่งอาหาร/ดูเมนูอาหาร

---

## หน้าที่
1. ไอซ์ : frontend
2. กัน : backend
3. กิต : backend
4. โอ๊ค : backend
5. เต : frontend

---

## ฟีเจอร์หลัก (Features) 
- ดูเมนูอาหาร (พร้อมตัวกรองตามหมวดหมู่)
- สั่งอาหาร & เพิ่มลงตะกร้า
- รวมราคาคำนวณยอดชำระ
- ระบบจัดการเมนู (Admin)

---
## Tech Stack

- **Frontend:** Python Framework (FastAPI + Jinja2 Templates + HTML/CSS)
- **Backend:** Python, Docker
- **Database:** PostgreSQL

---

## โครงสร้างโฟลเดอร์ (Project Structure)

```text
front_py/
├── main.py                    # Application entry point - รวม routers, mount static
├── app/
│   ├── core/
│   │   └── config.py         # การตั้งค่าแอป
│   ├── models/
│   │   └── menu_item.py    # MenuItem model
│   ├── services/
│   │   ├── menu_service.py    # จัดการข้อมูลเมนู (mock data 12 รายการ)
│   │   ├── cart_service.py    # จัดการตะกร้าผ่าน session
│   │   └── template_service.py
│   └── routers/
│       ├── menu_router.py     # หน้าดูเมนู + filter by category
│       ├── cart_router.py     # หน้าตะกร้า
│       └── admin_router.py    # หน้า admin จัดการเมนู
├── templates/                 # base, menu, cart, admin (Jinja2)
└── static/                    # css + รูปเมนู
requirements.txt
```

---

## วิธีรันโปรเจกต์ (Getting Started)

1. **install**
   ```
   pip install -r requirements.txt
   ```

2. **run**
   ```
   cd front_py
   python -m uvicorn main:app --reload
   ```
