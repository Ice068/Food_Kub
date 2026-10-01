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
├── front_py/                         # ระบบหน้าบ้าน (พอร์ต 8001)
│   ├── main.py                       # จุดรัน Frontend Web (FastAPI)
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py             # กำหนด BACKEND_URL
│   │   ├── routers/
│   │   │   ├── menu_router.py        # หน้าเมนู เมนูแนะนำ ตัวกรองหมวดหมู่ และวงล้อสุ่มอาหาร
│   │   │   ├── cart_router.py        # หน้าตะกร้าและการคำนวณราคา
│   │   │   └── admin_router.py       # หน้าเว็บ Admin จัดการเมนู
│   │   └── services/
│   │       ├── cart_service.py       # จัดการตะกร้าผ่าน Session
│   │       ├── template_service.py   # เรนเดอร์หน้าเว็บด้วย Jinja2
│   │       ├── menu_service.py       # ส่ง HTTP ขอข้อมูลเมนูจาก Backend
│   │       └── discovery_service.py  # เลือกเมนูแนะนำ เตรียม URL รูป และสุ่มผลวงล้อ
│   ├── templates/
│   │   ├── base.html                # โครงหน้าหลักและแถบนำทาง
│   │   ├── menu.html                # หน้าเมนูอาหารและเมนูแนะนำ
│   │   ├── random.html              # หน้าวงล้อสุ่มอาหารพร้อมเลือกหมวดหมู่
│   │   ├── cart.html                # หน้าตะกร้าสินค้า
│   │   ├── admin.html               # หน้าจัดการเมนูของ Admin
│   │   ├── login.html               # หน้าเข้าสู่ระบบ Admin
│   │   └── partials/
│   │       └── food_card.html       # Macro การ์ดอาหาร ใช้ร่วมกันหลายหน้า
│   └── static/
│       ├── style.css                # รูปแบบหลักของเว็บไซต์
│       ├── discovery.css            # รูปแบบเมนูแนะนำและแอนิเมชันวงล้อ
│       └── images/                  # รูปภาพที่จัดเก็บภายในโปรเจกต์
│
├── firebase-credentials.json # ไฟล์ยืนยันสิทธิ์การเข้าถึงฐานข้อมูล Firebase (ห้าม Commit ขึ้น Git)
├── requirements.txt         # ไฟล์ประกาศ Library ที่ใช้งาน (เพิ่ม httpx, firebase-admin, qrcode)
└── .gitignore               # ป้องกันคีย์และแคชขยะหลุดขึ้นสาธารณะ
```
## เมนูแนะนำและวงล้อสุ่มอาหาร

### เมนูแนะนำ
- แสดงเมนูที่ร้านเลือกไว้บนหน้าแรก `/`
- กำหนด ID และลำดับเมนูที่แนะนำได้ใน
  `front_py/app/services/discovery_service.py`

```python
RECOMMENDED_IDS = (1, 3, 7)
```

- ต้องใช้ ID ของเมนูที่มีอยู่จริงในระบบ
- ระบบจะข้าม ID ที่ไม่พบ โดยไม่ได้จัดอันดับจากยอดขาย

### วงล้อสุ่มอาหาร
- เข้าใช้งานผ่าน `/random` หรือเมนูนำทางบนเว็บไซต์
- ใช้ข้อมูลอาหารชุดเดียวกับหน้าร้าน
- เลือกสุ่มจากทุกหมวดหมู่ หรือเลือกหมวดแล้วกด “เลือกหมวด”
- กดสุ่มและรอแอนิเมชันประมาณ 4 วินาที
- เพิ่มอาหารที่สุ่มได้ลงตะกร้าผ่านปุ่ม “เพิ่มลงตะกร้า”
- หากมีอาหารเกิน 12 รายการ ระบบจะสุ่มมาแสดงบนวงล้อ
  12 รายการต่อครั้ง แล้วสุ่มผู้ชนะจากรายการเหล่านั้น
  โดยอาหารทุกเมนูในหมวดที่เลือกมีโอกาสชนะเท่ากัน

### เทคโนโลยี
- Python ประมวลผลการสุ่มที่ฝั่งเซิร์ฟเวอร์
- HTML และ Jinja2 แสดงรายการอาหารและผลการสุ่ม
- CSS แสดงแอนิเมชันวงล้อ โดยไม่ใช้ JavaScript
- การกดสุ่มแต่ละครั้งส่งฟอร์มและโหลดหน้าเว็บใหม่

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
