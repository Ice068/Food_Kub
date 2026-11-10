import json
import os
import firebase_admin
from firebase_admin import credentials, firestore


def _load_credential():
    cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if cred_json:
        return credentials.Certificate(json.loads(cred_json))

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    default_path = os.path.join(project_root, "firebase-credentials.json")
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", default_path)

    render_secret = "/etc/secrets/firebase-credentials.json"
    if not os.path.exists(cred_path) and os.path.exists(render_secret):
        cred_path = render_secret

    return credentials.Certificate(cred_path)


def get_db():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(_load_credential())
    return firestore.client()


db = get_db()
