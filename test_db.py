import firebase_admin
from firebase_admin import credentials, firestore

def init_db():
    try:
        # ตรวจสอบเพื่อป้องกัน initialization ซ้ำ
        if not firebase_admin._apps:
            # ใช้พาธของไฟล์ที่อยู่ใน root ของโปรเจกต์ (d:\Food_Kub)
            cred = credentials.Certificate("firebase-credentials.json")
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"เชื่อมต่อฐานข้อมูลล้มเหลว: {e}")
        return None

def test_connection():
    print("=== กำลังทดสอบเชื่อมต่อกับ Firebase Firestore... ===")
    db = init_db()
    if db is None:
        return
        
    print("เชื่อมต่อสำเร็จ! กำลังทดสอบเขียนข้อมูลลง Collection 'test_connection'...")
    
    # 1. เขียนข้อมูลทดสอบ
    doc_ref = db.collection("test_connection").document("status")
    doc_ref.set({
        "message": "Hello from Food_Kub Backend!",
        "connected_at": firestore.SERVER_TIMESTAMP,
        "status": "success"
    })
    print("เขียนข้อมูลสำเร็จ!")
    
    # 2. อ่านข้อมูลทดสอบ
    doc = doc_ref.get()
    if doc.exists:
        print(f"อ่านข้อมูลกลับมาได้: {doc.to_dict()}")
    else:
        print("ไม่พบเอกสารข้อมูล")

if __name__ == "__main__":
    test_connection()
