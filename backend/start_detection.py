import requests, time, sys
CAM_ID = '3510ee10-b72b-4c88-bec8-19378653587b'
BASE = 'http://localhost:8000'
print('Starting detection for Webcam Test...')
print('Waiting 4s for stream to stabilize...')
time.sleep(4)
try:
    r = requests.post(f'{BASE}/api/cameras/{CAM_ID}/start', timeout=10)
    r.raise_for_status()
    d = r.json()
    print('[OK] Detection started!')
    print('     Stream  : ' + str(d.get('stream_url')))
    print('     MediaMTX: ' + str(d.get('via_mediamtx')))
    print('')
    print('Buka: http://localhost:5173')
    print('Face Capture akan terisi dalam beberapa detik.')
except requests.exceptions.ConnectionError:
    print('[ERROR] Backend tidak jalan. Jalankan: uvicorn app.main:app --reload')
    sys.exit(1)
except Exception as e:
    print('[ERROR] ' + str(e))
    sys.exit(1)
