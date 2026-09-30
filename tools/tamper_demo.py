"""Demo step 6: flip one field of a stored record, then refresh the verify page: it turns INVALID.
ONLY run against a COPY of the database (set FIELDGUARD_DATA_DIR to a copy of data/).

  python -m tools.tamper_demo <record_id>            # changes result to the opposite value
  python -m tools.tamper_demo <record_id> --restore  # puts the original back
"""
import json, sys
from backend import db
from backend.config import DATA_DIR

BACKUP = DATA_DIR / ".tamper_backup.json"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rid, c = sys.argv[1], db.connect()
    row = c.execute("SELECT record_json FROM tests WHERE id=?", (rid,)).fetchone()
    if not row:
        sys.exit("no such record")
    if "--restore" in sys.argv:
        orig = json.loads(BACKUP.read_text())[rid]
        c.execute("UPDATE tests SET record_json=? WHERE id=?", (orig, rid)); print("restored")
        return
    BACKUP.write_text(json.dumps({rid: row["record_json"]}))
    rec = json.loads(row["record_json"]); rec["result"] = "NEGATIVE" if rec["result"] == "POSITIVE" else "POSITIVE"
    c.execute("UPDATE tests SET record_json=? WHERE id=?", (json.dumps(rec, sort_keys=True), rid))
    print(f"changed result to {rec['result']} inside {DATA_DIR}. Now open the verify page.")


if __name__ == "__main__":
    main()
