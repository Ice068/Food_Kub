# รายงานการแยกโค้ดเป็นระบบหน้าบ้าน (Frontend) และหลังบ้าน (Backend) อย่างอิสระ

เราได้แยกโครงสร้างของโปรเจกต์ Food_Kub ออกเป็น 2 โปรเจกต์ย่อยบน Branch `backend-firebase` เพื่อแบ่งหน้าที่หน้าบ้านและหลังบ้านอย่างชัดเจน

---

## 🏗️ โครงสร้างโฟลเดอร์ใหม่ (New Project Structure)

```text
Food_Kub/
├── blackend_py/              # [NEW] ระบบหลังบ้าน (พอร์ต 8000)
│   ├── main.py               # จุดรัน Backend API (FastAPI)
│   └── app/
│       ├── core/
│       │   ├── config.py
│       │   └── db.py         # ต่อ Firebase Firestore
│       ├── models/
│       │   └── menu_item.py
│       ├── routers/
│       │   ├── menu_api.py   # บริการ API ดึงเมนู /api/menu
│       │   └── admin_api.py  # บริการ API สำหรับหลังบ้าน /api/admin
│       └── services/
│           └── menu_service.py
│
├── front_py/                 # ระบบหน้าบ้าน (พอร์ต 8001)
│   ├── main.py               # จุดรัน Frontend Web (FastAPI + Jinja2)
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py     # กำหนดค่า BACKEND_URL = "http://localhost:8000"
│   │   ├── routers/
│   │   │   ├── menu_router.py   # ดึงข้อมูลจาก API หลังบ้านมาเรนเดอร์ HTML
│   │   │   ├── cart_router.py
│   │   │   └── admin_router.py
│   │   └── services/
│   │       ├── cart_service.py
│   │       ├── template_service.py
│   │       └── menu_service.py  # ทำหน้าที่เป็น Client ส่ง HTTP ขอข้อมูลจาก Backend
│   ├── templates/
│   └── static/
│
├── firebase-credentials.json # ไฟล์สิทธิ์การเข้าถึงฐานข้อมูล Firebase
└── requirements.txt         # ไฟล์ Library (เพิ่ม httpx และ firebase-admin)
```

---

## ⚡ วิธีการรันโปรเจกต์แยก 2 เซิร์ฟเวอร์

### 1. รันฝั่งหลังบ้าน (Backend API)
เปิด Terminal ที่ 1:
```bash
cd blackend_py
python -m uvicorn main:app --reload --port 8000
```
*ระบบจะรัน API อยู่ที่ http://localhost:8000*

### 2. รันฝั่งหน้าบ้าน (Frontend Web)
เปิด Terminal ที่ 2:
```bash
cd front_py
python -m uvicorn main:app --reload --port 8001
```
*ระบบเว็บเพจหลักจะเข้าได้ทาง http://localhost:8001*

---

## 🧪 ผลการทดสอบ (Verification)
- เมื่อสั่งรันทั้งคู่ ระบบหน้าบ้านที่พอร์ต `8001` สามารถเชื่อมโยงขอข้อมูลผ่าน API ไปยังหลังบ้านพอร์ต `8000` ได้สำเร็จ 100%
- ใน Log ของฝั่งหลังบ้าน ปรากฏการเรียกขอข้อมูล `GET /api/menu` และ `GET /api/menu/categories` สำเร็จเป็นรหัส `200 OK`
