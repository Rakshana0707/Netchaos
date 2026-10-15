import os
import sys
import json
import urllib.request
import urllib.error

# 1. Try resetting via running API first
API_URL = "http://localhost:8001/api/database/reset"
reset_via_api = False
try:
    req = urllib.request.Request(API_URL, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=2) as resp:
        if resp.status == 200:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[OK] Reset via running NetChaos API: {result.get('message', 'Done')}")
            reset_via_api = True
except Exception:
    pass

# 2. If API was not reachable or as direct fallback, reset via python database module directly
if not reset_via_api:
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    try:
        from app.database.database import reset_database
        res = reset_database()
        print(f"[OK] Reset database directly: {res.get('message', 'Done')}")
    except Exception as e:
        print(f"[ERROR] Could not reset database directly: {e}")
        sys.exit(1)

print("Original dataset has been successfully restored.")
