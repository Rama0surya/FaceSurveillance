import cv2, shutil, urllib.request

for i in range(3):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f'Camera {i}: OK ({int(w)}x{int(h)})')
        cap.release()
    else:
        print(f'Camera {i}: not found')

ffmpeg = shutil.which('ffmpeg')
print('ffmpeg: ' + (ffmpeg if ffmpeg else 'NOT FOUND'))

try:
    urllib.request.urlopen('http://localhost:9997/v3/paths/list', timeout=2)
    print('MediaMTX: RUNNING')
except:
    print('MediaMTX: NOT RUNNING')
