# หัวข้อ : ระบบสั่งอาหาร (Food_Kub)
## ระบบสั่งอาหาร / ดูเมนูอาหาร

---

## สมาชิกและหน้าที่ (Roles)
1. ไอซ์ : frontend
2. กัน : backend
3. กิต : backend
4. โอ๊ค : backend
5. เต : frontend

---

## ฟีเจอร์หลัก (Features)
- ดูเมนูอาหาร (พร้อมตัวกรองตามหมวดหมู่)
- สั่งอาหาร & เพิ่มลงตะกร้าสินค้า (ผ่าน Session)
- ระบบจัดการเมนูอาหาร (เพิ่ม/ลบเมนูอาหารในหน้า Admin)
- ระบบจ่ายเงินพร้อมเพย์ (สร้าง QR Code พร้อมเพย์สแกนจ่ายเงินจริงตามราคารวม) [Backend API]

---

## Tech Stack

- **Frontend Website:** Python FastAPI + Jinja2 Templates + HTML/CSS
- **Backend API:** Python FastAPI + Firebase Admin SDK
- **Database:** Firebase Firestore (Cloud Database)

---

## โครงสร้างโปรเจกต์ (Project Structure)

```text
Food_Kub/
├── blackend_py/              # ส่วนระบบหลังบ้าน (พอร์ต 8000)
│   ├── main.py               # จุดรัน Backend API (FastAPI)
│   └── app/
│       ├── core/
│       │   ├── config.py
│       │   └── db.py         # ตัวเชื่อมต่อ Firebase Firestore
│       ├── models/
│       │   └── menu_item.py  # โครงสร้างคลาส MenuItem
│       ├── routers/
│       │   ├── menu_api.py   # เส้นทาง API สำหรับดึงเมนูอาหาร
│       │   ├── admin_api.py  # เส้นทาง API สำหรับ Admin เพิ่ม/ลบเมนู
│       │   └── payment_api.py# เส้นทาง API เจน QR Code พร้อมเพย์
│       └── services/
│           └── menu_service.py # คลาสควบคุม Business Logic ติดต่อฐานข้อมูล
│
├── front_py/                 # ส่วนระบบหน้าบ้าน (พอร์ต 8001)
│   ├── main.py               # จุดรัน Frontend Web (FastAPI)
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py     # กำหนดค่าตัวแปรปลายทาง BACKEND_URL = "http://localhost:8000"
│   │   ├── routers/
│   │   │   ├── menu_router.py# หน้าดูเมนูอาหาร (ดึงข้อมูลจาก API หลังบ้านมาเรนเดอร์)
│   │   │   ├── cart_router.py# หน้าตะกร้าและการคำนวณราคาสินค้า
│   │   │   └── admin_router.py# หน้าเว็บ Admin จัดการเมนู
│   │   └── services/
│   │       ├── cart_service.py
│   │       ├── template_service.py
│   │       └── menu_service.py# ทำหน้าที่เป็น Client ส่ง HTTP ขอข้อมูลจาก Backend
│   ├── templates/            # ไฟล์โครงสร้างเว็บ HTML
│   └── static/               # ไฟล์ Stylesheet CSS และรูปภาพประกอบ
│
├── firebase-credentials.json # ไฟล์ยืนยันสิทธิ์การเข้าถึงฐานข้อมูล Firebase (ห้าม Commit ขึ้น Git)
├── requirements.txt         # ไฟล์ประกาศ Library ที่ใช้งาน (เพิ่ม httpx, firebase-admin, qrcode)
└── .gitignore               # ป้องกันคีย์และแคชขยะหลุดขึ้นสาธารณะ
```

---

## วิธีรันโปรเจกต์ (Getting Started)

### 1. ติดตั้งไลบรารีที่จำเป็น
รันคำสั่งติดตั้งแพ็กเกจทั้งหมดในระบบ:
```bash
pip install -r requirements.txt
```

### 2. รันระบบหลังบ้าน (Backend API)
เปิด Terminal ที่ 1:
```bash
cd blackend_py
python -m uvicorn main:app --reload --port 8000
```
*เซิร์ฟเวอร์หลังบ้านจะเปิดใช้งานที่ http://localhost:8000*

### 3. รันระบบหน้าบ้าน (Frontend Web)
เปิด Terminal ที่ 2:
```bash
cd front_py
python -m uvicorn main:app --reload --port 8001
```
*เซิร์ฟเวอร์หน้าบ้านจะเปิดใช้งานที่ http://localhost:8001*
