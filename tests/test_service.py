"""End-to-end tests of the service layer (no web server needed).  Run:  python -m unittest -v"""
import os, sqlite3, tempfile, unittest, json
from datetime import date, timedelta
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="fg_test_")
os.environ["FIELDGUARD_DATA_DIR"] = _TMP
os.environ["FIELDGUARD_SIGNING_KEY"] = "11" * 32
os.environ["FIELDGUARD_JWT_SECRET"] = "test-secret"

from backend import db, service, report                      # noqa: E402
from backend.config import load_kits                          # noqa: E402
from tools import simulate                                    # noqa: E402

USER = {"operator_id": "OFF-001"}
GOOD = (date.today() + timedelta(days=200)).isoformat()
KIT = load_kits()["kits"]["demo-swatch"]


def photo(cls="negative", light="daylight", seed=1):
    return simulate.render(KIT["classes"][cls], light, seed=seed)


def run(img, **kw):
    a = dict(kit_type="demo-swatch", kit_lot="LOT42", kit_expiry=GOOD, control_done=True, timer_seconds=30,
             gps={"lat": 19.09, "lng": 74.74, "accuracy": 8.0}, client_time="2026-09-30T10:00:00Z", device_id="test")
    a.update(kw)
    return service.create_test(USER, img, **a)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_1_result_and_chain(self):
        a = run(photo("negative", seed=1)); b = run(photo("positive", seed=2))
        self.assertEqual(a["record"]["result"], "NEGATIVE"); self.assertEqual(b["record"]["result"], "POSITIVE")
        self.assertEqual(b["record"]["prev_hash"], a["record"]["record_hash"])
        self.assertTrue(service.verify_test(a["record"]["id"])["valid"])
        self.assertTrue(service.verify_full_chain()["ok"])

    def test_2_blocks(self):
        with self.assertRaisesRegex(service.ServiceError, "expired"):
            run(photo(), kit_expiry=(date.today() - timedelta(days=1)).isoformat())
        with self.assertRaisesRegex(service.ServiceError, "Control"):
            run(photo(), control_done=False)
        with self.assertRaisesRegex(service.ServiceError, "Reading window"):
            run(photo(), timer_seconds=5)
        with self.assertRaisesRegex(service.ServiceError, "JPEG or PNG"):
            run(b"not an image")

    def test_3_retake_is_not_stored(self):
        n = len(service.list_tests())
        r = run(photo(light="flash"))
        self.assertEqual(r["status"], "RETAKE"); self.assertEqual(len(service.list_tests()), n)
        self.assertEqual(run(b"\xff\xd8\xff" + b"0" * 100)["status"], "RETAKE")

    def test_4_tamper_detected(self):
        rec = run(photo("negative", seed=5))["record"]
        c = db.connect()
        row = c.execute("SELECT record_json FROM tests WHERE id=?", (rec["id"],)).fetchone()
        edited = json.loads(row["record_json"]); edited["result"] = "POSITIVE"
        c.execute("UPDATE tests SET record_json=? WHERE id=?", (json.dumps(edited, sort_keys=True), rec["id"]))
        v = service.verify_test(rec["id"])
        self.assertFalse(v["valid"]); self.assertFalse(v["checks"]["hash_and_signature"])
        self.assertFalse(service.verify_full_chain()["ok"])
        c.execute("UPDATE tests SET record_json=? WHERE id=?", (row["record_json"], rec["id"]))   # restore
        # editing only the searchable column is caught too
        c.execute("UPDATE tests SET result='POSITIVE' WHERE id=?", (rec["id"],))
        self.assertFalse(service.verify_test(rec["id"])["checks"]["index_matches_record"])
        c.execute("UPDATE tests SET result='NEGATIVE' WHERE id=?", (rec["id"],))
        self.assertTrue(service.verify_test(rec["id"])["valid"])
        c.close()

    def test_5_deleted_record_and_swapped_image(self):
        ids = [run(photo("negative", seed=10 + i))["record"]["id"] for i in range(3)]
        c = db.connect(); c.execute("DELETE FROM tests WHERE id=?", (ids[1],))
        self.assertFalse(service.verify_test(ids[2])["checks"]["chain_link"])
        c.close()
        rec = run(photo("positive", seed=30))["record"]
        p = Path(db.connect().execute("SELECT image_path FROM tests WHERE id=?", (rec["id"],)).fetchone()[0])
        p.write_bytes(photo("negative", seed=31))
        self.assertFalse(service.verify_test(rec["id"])["checks"]["image_matches_hash"])

    def test_6_search_and_pdf(self):
        rec = run(photo("positive", seed=40), kit_lot="SEARCHME9")["record"]
        self.assertEqual([r["id"] for r in service.list_tests(q="SEARCHME9")], [rec["id"]])
        self.assertTrue(all(r["result"] == "POSITIVE" for r in service.list_tests(result="positive")))
        row = service.get_row(rec["id"])
        pdf = report.build_pdf(rec, f"http://x/#/verify/{rec['id']}", True, row["image_path"], row["annotated_path"])
        self.assertTrue(pdf.startswith(b"%PDF") and len(pdf) > 5000)


if __name__ == "__main__":
    unittest.main()
