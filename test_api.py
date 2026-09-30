import requests
import os
import sys

BASE_URL = "http://localhost:8000/api"

print("Login...")
resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "officer1", "password": "demo"})
if resp.status_code != 200:
    print("Login failed:", resp.text)
    sys.exit(1)
token = resp.json()["token"]
headers = {"Authorization": f"Bearer {token}"}
print("Login OK")

print("GET kits...")
resp = requests.get(f"{BASE_URL}/kits", headers=headers)
print("Kits:", resp.json())
kit_id = list(resp.json()["kits"])[0]["id"]

print("POST tests...")
photo_dir = "data/test_photos"
photos = [f for f in os.listdir(photo_dir) if f.endswith(".jpg")]
if not photos:
    print("No photos found in data/test_photos")
    sys.exit(1)

with open(os.path.join(photo_dir, photos[0]), "rb") as f:
    files = {"photo": ("photo.jpg", f, "image/jpeg")}
    data = {
        "kit_type": kit_id,
        "kit_lot": "LOT123",
        "kit_expiry": "2030-01-01",
        "control_done": True,
        "timer_seconds": 60,
    }
    resp = requests.post(f"{BASE_URL}/tests", headers=headers, files=files, data=data)

if resp.status_code != 200:
    print("POST tests failed:", resp.text)
    sys.exit(1)

print("POST response OK")
record_id = resp.json()["record"]["id"]
print("POST tests OK, record_id:", record_id)

print("GET tests...")
resp = requests.get(f"{BASE_URL}/tests", headers=headers)
print("Tests count:", len(resp.json()))

print(f"GET verify/{record_id}...")
resp = requests.get(f"{BASE_URL}/verify/{record_id}")
if resp.status_code != 200:
    print("GET verify failed:", resp.text)
    sys.exit(1)
print("Verify OK")

print(f"GET tests/{record_id}/report.pdf...")
resp = requests.get(f"{BASE_URL}/tests/{record_id}/report.pdf", headers=headers)
if resp.status_code != 200:
    print("GET PDF failed:", resp.text)
    sys.exit(1)
print("PDF OK, size:", len(resp.content))

print("GET verify-chain...")
resp = requests.get(f"{BASE_URL}/verify-chain")
if resp.status_code != 200:
    print("GET verify-chain failed:", resp.text)
    sys.exit(1)
print("Verify chain OK")

print("All API tests passed.")

