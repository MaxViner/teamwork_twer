import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.jobs import load_job
job = load_job("0cfa7047d77d428b9e1beb6616c484d6")
segs = job["stages"]["speech"]["result"]["segments"]
print("segments:", len(segs))
for s in segs[:15]:
    print(s["start"], "|", s["text"])
d = job["stages"]["location_evidence"]["result"]["dossier"]
print("country_candidates:", json.dumps(d.get("country_candidates"), ensure_ascii=False)[:800])
print("places keys:", d.get("places"))
