from __future__ import annotations
import json, random, uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from app.core.db_client import get_db

EMOTIONS   = ["happy","neutral","sad","angry","surprise","fear","disgust"]
GENDERS    = ["male","female"]
AGE_GROUPS = ["anak","remaja","dewasa","lansia"]
AGE_RANGES = {"anak":(4,12),"remaja":(13,17),"dewasa":(18,59),"lansia":(60,85)}
CAMERA_NAMES = ["Lobby Utama","Pintu Masuk","Area Parkir"]
CAMERA_URLS  = ["rtsp://192.168.1.10:554/stream1","rtsp://192.168.1.11:554/stream1","rtsp://192.168.1.12:554/stream1"]

def generate_mock_data(num_detections=100, hours_span=48) -> dict:
    db = get_db(); now = datetime.now(timezone.utc)
    try:
        camera_ids = []
        existing = {r["name"]: r["id"] for r in db.execute(text("SELECT id,name FROM cameras")).mappings().all()}
        for i, name in enumerate(CAMERA_NAMES):
            if name in existing:
                camera_ids.append(existing[name])
            else:
                cid = str(uuid.uuid4())
                db.execute(text("INSERT INTO cameras (id,name,rtsp_url,status,created_at) VALUES (:id,:n,:u,'offline',:t)"),
                           {"id":cid,"n":name,"u":CAMERA_URLS[i],"t":now.isoformat()})
                camera_ids.append(cid)
        for cid in existing.values():
            if cid not in camera_ids: camera_ids.append(cid)
        db.commit()

        det_count = snap_count = 0; buckets = {}
        for _ in range(num_detections):
            cam = random.choice(camera_ids)
            ts = now - timedelta(seconds=random.randint(0, hours_span*3600))
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            faces = []
            for _ in range(random.randint(1,3)):
                g = random.choice(GENDERS); e = random.choice(EMOTIONS)
                ag = random.choices(AGE_GROUPS, weights=[10,15,55,20], k=1)[0]
                age = random.randint(*AGE_RANGES[ag]); fid = str(uuid.uuid4())
                faces.append({"id":fid,"bbox":{"x":random.randint(50,500),"y":random.randint(30,400),"w":random.randint(60,150),"h":random.randint(60,180)},
                              "gender":g,"emotion":e,"age_group":ag,"age":age,
                              "confidence":round(random.uniform(0.70,0.99),2),"snapshot_url":f"/snapshots/mock/{fid[:8]}.jpg"})
                hb = ts.replace(minute=0,second=0,microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                k = f"{cam}|{hb}"
                if k not in buckets: buckets[k]={"camera_id":cam,"hour_bucket":hb,"total":0,"male":0,"female":0,"emotions":{},"age_groups":{}}
                b=buckets[k]; b["total"]+=1
                if g=="male": b["male"]+=1
                else: b["female"]+=1
                b["emotions"][e]=b["emotions"].get(e,0)+1; b["age_groups"][ag]=b["age_groups"].get(ag,0)+1
            did = str(uuid.uuid4())
            db.execute(text("INSERT INTO detections (id,camera_id,timestamp,faces) VALUES (:id,:c,:t,:f)"),
                       {"id":did,"c":cam,"t":ts_str,"f":json.dumps(faces)}); det_count+=1
            for face in faces:
                db.execute(text("INSERT INTO snapshots (id,camera_id,detection_id,url,created_at) VALUES (:id,:c,:d,:u,:t)"),
                           {"id":str(uuid.uuid4()),"c":cam,"d":did,"u":face["snapshot_url"],"t":ts_str}); snap_count+=1
        db.commit()

        sc = 0
        for key, b in buckets.items():
            row = db.execute(text("SELECT id,total,male,female,emotions,age_groups FROM hourly_stats WHERE camera_id=:c AND hour_bucket=:h LIMIT 1"),
                             {"c":b["camera_id"],"h":b["hour_bucket"]}).mappings().first()
            if row:
                row=dict(row)
                emos = json.loads(row["emotions"]) if isinstance(row["emotions"],str) else (row["emotions"] or {})
                ags  = json.loads(row["age_groups"]) if isinstance(row["age_groups"],str) else (row["age_groups"] or {})
                for k,v in b["emotions"].items():   emos[k]=emos.get(k,0)+v
                for k,v in b["age_groups"].items(): ags[k]=ags.get(k,0)+v
                db.execute(text("UPDATE hourly_stats SET total=total+:t,male=male+:m,female=female+:f,emotions=:e,age_groups=:a WHERE id=:id"),
                           {"t":b["total"],"m":b["male"],"f":b["female"],"e":json.dumps(emos),"a":json.dumps(ags),"id":row["id"]})
            else:
                db.execute(text("INSERT INTO hourly_stats (id,camera_id,hour_bucket,total,male,female,emotions,age_groups) VALUES (:id,:c,:h,:t,:m,:f,:e,:a)"),
                           {"id":str(uuid.uuid4()),"c":b["camera_id"],"h":b["hour_bucket"],"t":b["total"],"m":b["male"],"f":b["female"],
                            "e":json.dumps(b["emotions"]),"a":json.dumps(b["age_groups"])})
            sc+=1
        db.commit()
        return {"cameras":len(camera_ids),"detections":det_count,"snapshots":snap_count,"hourly_stats_buckets":sc}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()