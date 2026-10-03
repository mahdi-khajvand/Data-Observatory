from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Some sandboxed filesystems break sqlite journals — fall back to /tmp
_candidate = DATA_DIR / "observatory.db"
try:
    import sqlite3
    _c = sqlite3.connect(str(_candidate))
    _c.execute("PRAGMA journal_mode=MEMORY")
    _c.execute("CREATE TABLE IF NOT EXISTS _ping (x INTEGER)")
    _c.commit()
    _c.close()
    DB_PATH = _candidate
except Exception:
    DB_PATH = Path("/tmp/data_observatory.db")

APP_NAME = "Data Observatory"
APP_TAGLINE = "Enterprise Data Platform"
SECRET = os.environ.get("DO_SECRET", "data-observatory-secret")
