import os, json, secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FIELDGUARD_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "fieldguard.db"
KITS_PATH = ROOT / "data" / "kits.json"
CARD_REF_PATH = DATA_DIR / "card_reference.json"
FRONTEND_DIR = ROOT / "frontend"
GENESIS_HASH = "0" * 64
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

for d in (DATA_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _persisted_secret(env_name, filename, nbytes=32):
    """Prefer the environment variable (production). For local dev only, generate a
    secret once and keep it in data/ (which is git-ignored) so restarts don't break
    tokens and records. Never commit these files."""
    val = os.environ.get(env_name)
    if val:
        return val
    f = DATA_DIR / filename
    if f.exists():
        return f.read_text().strip()
    val = secrets.token_hex(nbytes)
    f.write_text(val)
    print(f"[fieldguard] WARNING: {env_name} not set; generated a dev secret in {f}. "
          f"Set {env_name} as an environment variable in production.")
    return val


def signing_key_hex():
    return _persisted_secret("FIELDGUARD_SIGNING_KEY", "dev_signing_key.hex")


def jwt_secret():
    return _persisted_secret("FIELDGUARD_JWT_SECRET", "dev_jwt_secret.txt")


def load_kits():
    return json.loads(KITS_PATH.read_text())
