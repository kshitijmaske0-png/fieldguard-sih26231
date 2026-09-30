import hashlib, hmac, os, secrets, sqlite3, threading
from .config import DB_PATH, GENESIS_HASH

_write_lock = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL,
  pw_hash TEXT NOT NULL, operator_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tests(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, record_json TEXT NOT NULL,
  record_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, result TEXT NOT NULL, operator_id TEXT NOT NULL,
  server_time_utc TEXT NOT NULL, kit_type TEXT NOT NULL, kit_lot TEXT NOT NULL,
  image_path TEXT NOT NULL, annotated_path TEXT);
CREATE INDEX IF NOT EXISTS idx_tests_time ON tests(server_time_utc);
CREATE INDEX IF NOT EXISTS idx_tests_result ON tests(result);
"""


def connect():
    c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)   # autocommit; we BEGIN manually
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    c = connect(); c.executescript(SCHEMA); c.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return salt, h


def check_password(password, salt, expected):
    return hmac.compare_digest(hash_password(password, salt)[1], expected)


def seed_users():
    """Creates 3 demo officers if the users table is empty. Password comes from
    FIELDGUARD_DEMO_PASSWORD, else a random one is printed ONCE to the server console."""
    c = connect()
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        pw = os.environ.get("FIELDGUARD_DEMO_PASSWORD") or secrets.token_urlsafe(8)
        for i in (1, 2, 3):
            salt, h = hash_password(pw)
            c.execute("INSERT INTO users(username,salt,pw_hash,operator_id,name) VALUES(?,?,?,?,?)",
                      (f"officer{i}", salt, h, f"OFF-{i:03d}", f"Demo Officer {i}"))
        print(f"[fieldguard] seeded users officer1..officer3, password: {pw}")
    c.close()


def get_user(username):
    c = connect(); r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone(); c.close()
    return r


def insert_test_chained(build_record, image_path, annotated_path):
    """build_record(prev_hash) -> record dict. The lock plus BEGIN IMMEDIATE means two tests
    can never take the same prev_hash."""
    with _write_lock:
        c = connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT record_hash FROM tests ORDER BY seq DESC LIMIT 1").fetchone()
            rec = build_record(row["record_hash"] if row else GENESIS_HASH)
            import json
            c.execute(
                "INSERT INTO tests(id,record_json,record_hash,prev_hash,result,operator_id,server_time_utc,"
                "kit_type,kit_lot,image_path,annotated_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rec["id"], json.dumps(rec, sort_keys=True), rec["record_hash"], rec["prev_hash"], rec["result"],
                 rec["operator_id"], rec["server_time_utc"], rec["kit_type"], rec["kit_lot"],
                 str(image_path), str(annotated_path) if annotated_path else None))
            c.execute("COMMIT")
            return rec
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()
