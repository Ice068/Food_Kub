# เชื่อมต่อระบบสั่งอาหารเข้ากับ Firebase Firestore

เปลี่ยนการเก็บข้อมูลของเมนูอาหารจากการบันทึกในหน่วยความจำชั่วคราว (Mock Data) ไปใช้งานฐานข้อมูลจริงบน Firebase Firestore โดยใช้ไฟล์สิทธิ์การเข้าถึง `firebase-credentials.json` ที่มีอยู่แล้ว

## Proposed Changes

### Database Integration

#### [NEW] [db.py](file:///d:/Food_Kub/front_py/app/core/db.py)
สร้างไฟล์สำหรับเริ่มต้นเชื่อมต่อ Firebase Firestore โดยคำนวณพาธของ `firebase-credentials.json` แบบอ้างอิงตำแหน่งจริงของโปรเจกต์ เพื่อไม่ให้เกิดปัญหาเมื่อรันจากโฟลเดอร์อื่น

```python
import os
import firebase_admin
from firebase_admin import credentials, firestore

def get_db():
    if not firebase_admin._apps:
        # หาตำแหน่ง root ของโปรเจกต์ (d:\Food_Kub) เพื่อระบุตำแหน่ง credentials
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
        cred_path = os.path.join(project_root, "firebase-credentials.json")
        
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = get_db()
```

#### [MODIFY] [menu_service.py](file:///d:/Food_Kub/front_py/app/services/menu_service.py)
แก้ไขคลาส `MenuService` ให้ใช้ฐานข้อมูลแทนลิสต์ในหน่วยความจำ:
- ตรวจสอบคอลเลกชัน `menu_items` ใน Firestore เมื่อเริ่มต้น หากยังไม่มีข้อมูล (เป็นฐานข้อมูลว่างเปล่า) จะททำการอัปโหลดข้อมูลเริ่มต้น (Seed Data) 12 รายการเข้าไปให้อัตโนมัติ
- ปรับฟังก์ชันดึงข้อมูล ดึงหมวดหมู่ เพิ่มข้อมูล และลบข้อมูลให้เรียกใช้ Firestore API

## Verification Plan

### Manual Verification
1. รันเซิร์ฟเวอร์โดยใช้คำสั่ง:
   ```bash
   cd front_py
   python -m uvicorn main:app --reload
   ```
2. เปิดเบราว์เซอร์ไปที่หน้าร้านค้าและหน้า Admin ตรวจสอบว่ามีข้อมูลอาหารครบ 12 รายการแสดงขึ้นมา
3. ทดลองกดลบอาหารในหน้า Admin แล้วเช็กดูว่าในระบบและหน้าหลักอาหารหายไปจริงไหม
4. ทดลองกดเพิ่มอาหารใหม่ในหน้า Admin พร้อมอัปโหลดรูปภาพ เช็กว่าอัปโหลดและเพิ่มเข้าฐานข้อมูลจริง
