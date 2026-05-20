from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import text
from app.core.db_client import get_db


def _hour_bucket(dt=None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()

def _j(v) -> dict:
    if not v: return {}
    if isinstance(v, dict): return v
    try: return json.loads(v)
    except: return {}


def upsert_hourly_stats(camera_id: str, gender: str, emotion: str, age_group: str) -> None:
    db = get_db()
    try:
        hour = _hour_bucket()
        row = db.execute(text("""
            SELECT * FROM hourly_stats WHERE camera_id = :c AND hour_bucket = :h LIMIT 1
        """), {"c": camera_id, "h": hour}).mappings().first()
        if row:
            row = dict(row)
            emos = _j(row.get("emotions")); ags = _j(row.get("age_groups"))
            emos[emotion] = emos.get(emotion, 0) + 1
            ags[age_group] = ags.get(age_group, 0) + 1
            db.execute(text("""
                UPDATE hourly_stats SET total=total+1, male=male+:m, female=female+:f,
                    emotions=:e, age_groups=:a WHERE id=:id
            """), {"m": 1 if gender=="Man" else 0, "f": 1 if gender=="Woman" else 0,
                   "e": json.dumps(emos), "a": json.dumps(ags), "id": row["id"]})
        else:
            db.execute(text("""
                INSERT INTO hourly_stats (id,camera_id,hour_bucket,total,male,female,emotions,age_groups)
                VALUES (:id,:c,:h,:t,:m,:f,:e,:a)
            """), {"id": str(uuid.uuid4()), "c": camera_id, "h": hour, "t": 1,
                   "m": 1 if gender=="Man" else 0, "f": 1 if gender=="Woman" else 0,
                   "e": json.dumps({emotion: 1}), "a": json.dumps({age_group: 1})})
        db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def get_today_stats(camera_id=None) -> list[dict]:
    db = get_db()
    try:
        today = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        params = {"today": today}
        cf = ""
        if camera_id: cf = "AND camera_id = :c"; params["c"] = camera_id
        rows = db.execute(text(f"SELECT * FROM hourly_stats WHERE hour_bucket >= :today {cf}"), params).mappings().all()
        agg = {}
        for row in rows:
            row = dict(row); cid = row["camera_id"]
            if cid not in agg:
                agg[cid] = {"camera_id": cid, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "total": 0, "male": 0, "female": 0, "emotions": {}, "age_groups": {}}
            b = agg[cid]; b["total"] += row.get("total",0); b["male"] += row.get("male",0); b["female"] += row.get("female",0)
            for k,v in _j(row.get("emotions")).items(): b["emotions"][k] = b["emotions"].get(k,0)+v
            for k,v in _j(row.get("age_groups")).items(): b["age_groups"][k] = b["age_groups"].get(k,0)+v
        return list(agg.values())
    finally:
        db.close()


def get_hourly_stats(camera_id=None, date=None) -> list[dict]:
    db = get_db()
    try:
        if date:
            ds = datetime.fromisoformat(date).replace(hour=0,minute=0,second=0,microsecond=0,tzinfo=timezone.utc)
        else:
            ds = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        de = ds + timedelta(days=1)
        params = {"ds": ds.isoformat(), "de": de.isoformat()}
        cf = ""
        if camera_id: cf = "AND camera_id = :c"; params["c"] = camera_id
        rows = db.execute(text(f"""
            SELECT * FROM hourly_stats WHERE hour_bucket >= :ds AND hour_bucket < :de {cf}
            ORDER BY hour_bucket ASC
        """), params).mappings().all()
        result = []
        for row in rows:
            row = dict(row); row["emotions"] = _j(row.get("emotions")); row["age_groups"] = _j(row.get("age_groups"))
            hb = str(row.get("hour_bucket",""))
            try: row["hour"] = datetime.fromisoformat(hb).hour
            except: row["hour"] = None
            row["date"] = ds.strftime("%Y-%m-%d"); row["hour_bucket"] = hb
            result.append(row)
        return result
    finally:
        db.close()


def get_comparison_stats(camera_id=None) -> dict:
    db = get_db()
    try:
        now = datetime.now(timezone.utc)
        ts = now.replace(hour=0,minute=0,second=0,microsecond=0)
        ys = ts - timedelta(days=1)
        cf = ""; p_t = {"s": ts.isoformat()}; p_y = {"s": ys.isoformat(), "e": ts.isoformat()}
        if camera_id:
            cf = "AND camera_id = :c"; p_t["c"] = camera_id; p_y["c"] = camera_id
        today_total = db.execute(text(f"SELECT COALESCE(SUM(total),0) FROM hourly_stats WHERE hour_bucket >= :s {cf}"), p_t).scalar() or 0
        yest_total  = db.execute(text(f"SELECT COALESCE(SUM(total),0) FROM hourly_stats WHERE hour_bucket >= :s AND hour_bucket < :e {cf}"), p_y).scalar() or 0
        if yest_total > 0:
            pct = round(((today_total - yest_total) / yest_total) * 100, 1)
        else:
            pct = 100.0 if today_total > 0 else 0.0
        return {"today": {"total": int(today_total)}, "yesterday": {"total": int(yest_total)}, "change_pct": pct}
    finally:
        db.close()