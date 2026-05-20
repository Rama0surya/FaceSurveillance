import requests
CAM_ID = '3510ee10-b72b-4c88-bec8-19378653587b'
BASE = 'http://localhost:8000'
try:
    r = requests.post(f'{BASE}/api/cameras/{CAM_ID}/stop', timeout=10)
    r.raise_for_status()
    print('[OK] Detection stopped')
except Exception as e:
    print('[ERROR] ' + str(e))
