# หัวข้อ : ระบบสั่งอาหาร (Food_Kub)

## QR Code แยกโต๊ะและกำหนดจำนวนโต๊ะ

- ติดตั้ง dependencies ด้วย `pip install -r requirements.txt`
- เข้าสู่ระบบ Admin แล้วกด **จัดการ QR Code ประจำโต๊ะ** หรือเปิด `/admin/tables`
- กำหนด **จำนวนโต๊ะ** ได้ 1–100 โต๊ะ (เริ่มต้น 5) แล้วกดสร้าง QR เช่น 10 โต๊ะจะได้ QR โต๊ะ 1–10 จำนวนที่เลือกอยู่ใน URL ของหน้าสร้าง QR และลดจำนวนพิมพ์จะไม่ลบตะกร้าเดิม
- ใส่ URL ของ frontend ที่มือถือเข้าถึงได้ เช่น `http://192.168.1.20:8001` (เปลี่ยนเป็น IP จริง) หรือโดเมน HTTPS ของร้าน แล้วกดสร้างและพิมพ์ QR
- ตั้ง URL เริ่มต้นได้ด้วย environment variable `PUBLIC_BASE_URL`
- QR เปิด `/?table=1` ถึง `/?table=N` ตามจำนวนที่เลือก เลขโต๊ะอยู่ใน URL และติดไปกับลิงก์เมนู หมวดหมู่ ตะกร้า และฟอร์มเพิ่ม/แก้ไขสินค้า จึงเปิดหลายโต๊ะในคนละแท็บได้
- ตะกร้าเก็บใน Session แยกตามเลขโต๊ะของ URL สแกนกลับโต๊ะเดิมจะเห็นรายการเดิม ตะกร้าแต่ละมือถือยังแยกกันแม้อยู่โต๊ะเดียวกัน
- หน้า `/` และ `/cart` ที่ไม่มี `?table=` ใช้ตะกร้าที่ไม่ระบุโต๊ะ แยกจากทุกโต๊ะเสมอ ปุ่ม **ทุกหมวดหมู่** เปลี่ยนเฉพาะหมวดอาหารและยังคงเลขโต๊ะเดิม
- เปิดเว็บโดยไม่สแกนยังดูเมนูได้ แต่จะแสดงว่ายังไม่ได้ระบุโต๊ะ ตะกร้าเดิมที่ไม่มีเลขโต๊ะจะไม่ถูกย้ายไปโต๊ะใดอัตโนมัติ
- เลขโต๊ะติดไปถึงหน้า checkout ผลการชำระเงิน ปุ่มลองอีกครั้ง และปุ่มล้างตะกร้า โดยใช้ระบบเงินสด/QR พร้อมเพย์ที่มีใน dev; QR ประจำโต๊ะใช้เปิดเมนู แยกจาก QR พร้อมเพย์ที่ใช้ชำระเงิน

ทดสอบในร้าน: รัน backend บนพอร์ต 8000 ตามการตั้งค่าปัจจุบัน และรัน frontend จากโฟลเดอร์ `front_py` ด้วย `python -m uvicorn main:app --host 0.0.0.0 --port 8001` มือถือต้องอยู่ Wi-Fi เดียวกันและเข้าถึงพอร์ต 8001 ได้ ห้ามใช้ `localhost` ใน QR สำหรับมือถือ

ทดสอบอัตโนมัติจากรากโปรเจกต์: `python -B -m unittest discover -s tests -v` (ใช้ข้อมูลเมนูจำลอง ไม่เชื่อม Firebase)

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
