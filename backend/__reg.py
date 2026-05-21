from app.core.db_client import get_db
from sqlalchemy import text
import uuid
from datetime import datetime, timezone
db = get_db()
try:
    row = db.execute(text("SELECT id FROM cameras WHERE name = 'Webcam Test' LIMIT 1")).mappings().first()
    if row:
        print('EXISTS:' + str(row['id']))
    else:
        cid = str(uuid.uuid4())
        db.execute(text("INSERT INTO cameras (id, name, rtsp_url, status, created_at) VALUES (:id, :n, :u, 'offline', :t)"),
            {'id': cid, 'n': 'Webcam Test', 'u': 'rtsp://localhost:8554/webcam', 't': datetime.now(timezone.utc).isoformat()})
        db.commit()
        print('CREATED:' + cid)
finally:
    db.close()
