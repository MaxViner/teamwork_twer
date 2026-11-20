import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.jobs import load_job

job = load_job("0cfa7047d77d428b9e1beb6616c484d6")
for name in ("location_evidence", "speech", "scenes", "road_geometry"):
    stage = job["stages"].get(name, {})
    obs = stage.get("observations") or []
    print("=" * 40, name, "status", stage.get("status"), "obs", len(obs))
    for item in obs[:4]:
        print(json.dumps({k: item.get(k) for k in ("start","end","source","text","data")}, ensure_ascii=False)[:600])
    res = stage.get("result") or {}
    print("RESULT KEYS:", list(res.keys())[:20])
    if name == "location_evidence":
        d = res.get("dossier") or {}
        print("PLACE CANDIDATES:", json.dumps(d.get("place_candidates"), ensure_ascii=False)[:1200])
