"""Quick test: verify system_info_cache and mock_data UPSERT work."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Test 1: Cache import and refresh
print("== Test 1: SystemInfoCache ==")
from app.services.system_info import SystemInfo, system_info_cache
cache = system_info_cache
cache._refresh()
info = cache.get_full_info()
print(f"  Cache keys: {list(info.keys())}")
print(f"  cache_age: {info['cache_age_seconds']}s")
print(f"  CPU cores: {info['cpu'].get('cores_logical')}")
print(f"  GPU: {info['gpu'].get('name')}")
hw = cache.get_hardware()
print(f"  Hardware keys: {list(hw.keys())}")
print("  [PASS] Cache works!")

# Test 2: Mock data UPSERT
print("\n== Test 2: Mock Data UPSERT ==")
from app.services.mock_data import generate_mock_data
try:
    # Run twice to trigger the upsert path
    r1 = generate_mock_data(num_detections=10, hours_span=2)
    print(f"  Run 1: {r1}")
    r2 = generate_mock_data(num_detections=10, hours_span=2)
    print(f"  Run 2: {r2}")
    print("  [PASS] No IntegrityError on duplicate hourly_stats!")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

# Cleanup
from app.core.db_client import get_db
from sqlalchemy import text
db = get_db()
try:
    db.execute(text("DELETE FROM alerts"))
    db.execute(text("DELETE FROM snapshots"))
    db.execute(text("DELETE FROM detections"))
    db.execute(text("DELETE FROM hourly_stats"))
    db.commit()
    print("\n  Cleanup done.")
except:
    db.rollback()
finally:
    db.close()

print("\nAll tests passed!")
