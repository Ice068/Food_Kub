# หัวข้อ : ระบบสั่งอาหาร (Food_Kub)

## Liquid Glass edition · รันฉบับปรับปรุง

แอปใช้ FastAPI, Jinja2 และ JavaScript/CSS โดยตรง ไม่ต้องใช้ Node.js หรือขั้นตอน build
รองรับการค้นหาเมนู ตัวกรอง จานโปรด ธีมสว่าง/มืด ตะกร้าแยกโต๊ะ ส่งครัว แบ่งบิล และจัดการร้าน

### ทดลองบนเครื่องโดยไม่เชื่อม Firebase

```powershell
python -m pip install -r requirements.txt
$env:FOOD_KUB_DEMO = "1"
python -m uvicorn main:app --app-dir front_py --host 127.0.0.1 --port 8001
```

เปิด `http://127.0.0.1:8001` หรือ `http://127.0.0.1:8001/?table=1` เพื่อทดลองสั่งที่โต๊ะ
หน้า `/admin/login` ในโหมดทดลองใช้ชื่อ `admin` และรหัสผ่าน `demo-food-kub`
ข้อมูลเมนู สถานะครัว โต๊ะ และประวัติการทดลองเก็บใน `.data/demo.sqlite3` และคงอยู่เมื่อเริ่มใหม่
การชำระเงินในโหมดนี้เป็นการจำลองเท่านั้น ไม่สร้าง QR ธนาคารและไม่เรียกเก็บเงินจริง
ยอดรายงานเริ่มต้นที่ศูนย์และคำนวณจากการทำรายการจริงในโหมดทดลอง

### ใช้งานกับ Backend เดิม

ปิด `FOOD_KUB_DEMO` หรือกำหนดเป็น `0` แล้วรัน Backend และ Frontend ตามวิธีด้านล่าง
ตั้งค่า `FOOD_KUB_ADMIN_PASSWORD` ก่อนเข้าสู่ระบบผู้ดูแล; เปลี่ยนชื่อบัญชีผ่าน `FOOD_KUB_ADMIN_USERNAME` ได้
ตั้ง `FOOD_KUB_SESSION_SECRET` เป็นค่าลับที่คงที่และ `FOOD_KUB_COOKIE_SECURE=1` เมื่อใช้ HTTPS
หากไม่กำหนด session secret ระบบจะสร้างคีย์สุ่มไว้ใน `.data/session.key` เพื่อรักษาเซสชันเมื่อรีสตาร์ต
ตั้ง `FOOD_KUB_BACKEND_URL` ได้หาก Backend ไม่ได้อยู่ที่ `http://localhost:8000`

คำขอรับเงินสดและการสร้าง QR พร้อมเพย์มีสถานะรอยืนยัน พนักงานต้องตรวจสอบยอดเงินจริง
แล้วกดยืนยันรับเงินในแดชบอร์ด ระบบจะไม่ถือว่าการสร้าง QR เป็นหลักฐานว่าได้รับเงินแล้ว
การยืนยันเงินจริงจากผู้ให้บริการธนาคารยังต้องเชื่อมต่อกับระบบของร้าน

### Deploy branch `kit` บน Render

สร้าง Web Service ที่ใช้ Python โดยเลือก branch `kit`, เว้น Root Directory ว่าง,
ตั้ง Build Command เป็น `pip install -r requirements.txt` และ Start Command เป็น `bash start_render.sh`
ใน Settings ตั้ง Health Check Path เป็น `/healthz` เพื่อให้ตรวจสอบการอ่านเมนูจาก Backend ด้วย
การสร้าง service ผ่านหน้าเว็บต้องตั้งค่าต่าง ๆ เอง; `render.yaml` ใช้กับการสร้างผ่าน Blueprint

ก่อน deploy ให้ไปที่ Environment → Secret Files → Add Secret File:

- Filename: `firebase-credentials.json`
- Contents: เนื้อหา JSON ทั้งไฟล์ของ Firebase service account ของโปรเจกต์นี้
- กด Save Changes เพื่อ redeploy; แอปรองรับไฟล์ที่ `/etc/secrets/firebase-credentials.json` อยู่แล้ว

อีกวิธีคือกำหนด Environment Variable `FIREBASE_CREDENTIALS_JSON` เป็นเนื้อหา JSON ทั้งไฟล์
เลือกใช้วิธีใดวิธีหนึ่ง และห้าม commit ไฟล์ credentials หรือวางค่าลับใน log/chat
ตั้ง `FOOD_KUB_ADMIN_PASSWORD`, `FOOD_KUB_SESSION_SECRET` และ `FOOD_KUB_COOKIE_SECURE=1`
สำหรับการใช้งานจริงด้วย

หากพบ `FileNotFoundError ... firebase-credentials.json` ตามด้วยหน้า `/` ตอบ `503`
สาเหตุคือ Backend ไม่มี credentials บน Render แม้ CSS/JS ยังโหลดได้
สคริปต์เริ่มระบบจะรอจน Backend อ่านเมนูได้ก่อนเปิด Frontend
และหยุด service พร้อมแสดง error หาก process ใดหยุดทำงาน
การเพิ่ม credentials ยังจำเป็น; สคริปต์ไม่สลับไปใช้ข้อมูลทดลองโดยอัตโนมัติ

หากต้องการเฉพาะเว็บทดลอง ให้ตั้ง `FOOD_KUB_DEMO=1` โดยไม่ต้องตั้ง Firebase
ข้อมูล SQLite ของโหมดทดลองบน Render ที่ไม่มี persistent disk จะหายเมื่อ redeploy/restart
จึงไม่เหมาะสำหรับเก็บคำสั่งซื้อจริง

อ้างอิง: [Render Secret Files](https://render.com/docs/configure-environment-variables#secret-files),
[Render Health Checks](https://render.com/docs/health-checks)

### ตรวจสอบ

```powershell
python -B -m unittest discover -s tests -v
python -m compileall -q front_py blackend_py tests
```

ชุดทดสอบใช้ API จำลองและฐานข้อมูลชั่วคราว ไม่เขียนข้อมูลลง Firebase
บน Windows ที่จำกัดการสร้าง local socket ให้รันจากเทอร์มินัลที่อนุญาต local networking

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
