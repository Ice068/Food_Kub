"""Runtime configuration shared by the web application and local demo."""
import os
import secrets
from pathlib import Path


class Settings:
    ROOT = Path(__file__).resolve().parents[3]
    APP_TITLE = "Food Kub · A little taste of happiness"
    TEMPLATES_DIR = str(ROOT / "front_py" / "templates")
    STATIC_DIR = str(ROOT / "front_py" / "static")
    STATIC_URL = "/static"
    BACKEND_URL = os.environ.get("FOOD_KUB_BACKEND_URL", "http://localhost:8000").rstrip("/")
    DEMO_MODE = os.environ.get("FOOD_KUB_DEMO", "0") == "1"
    DEMO_DB = Path(os.environ.get("FOOD_KUB_DEMO_DB", str(ROOT / ".data" / "demo.sqlite3")))
    COOKIE_SECURE = os.environ.get("FOOD_KUB_COOKIE_SECURE", "0") == "1"

    @property
    def SESSION_SECRET(self) -> str:
        configured = os.environ.get("FOOD_KUB_SESSION_SECRET")
        if configured:
            return configured
        path = self.ROOT / ".data" / "session.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        return path.read_text(encoding="utf-8").strip()


settings = Settings()
