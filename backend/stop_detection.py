import requests
CAM_ID = '3ef7bf84-70ae-425e-a9d3-9ecc5e0dfbea'
BASE = 'http://localhost:8000'
try:
    r = requests.post(f'{BASE}/api/cameras/{CAM_ID}/stop', timeout=10)
    r.raise_for_status()
    print('[OK] Detection stopped')
except Exception as e:
    print('[ERROR] ' + str(e))
