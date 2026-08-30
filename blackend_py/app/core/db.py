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
