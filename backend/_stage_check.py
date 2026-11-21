import sys, json, traceback
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.jobs import load_job, job_folder
from app.stages.summary import extract_summary
from app.stages.video_structure import extract_video_structure
from app.stages.comprehension import extract_comprehension
from app.stages.landmarks import extract_landmarks
from app.search import search_job

jid = "0cfa7047d77d428b9e1beb6616c484d6"
job = load_job(jid)
folder = job_folder(jid)
run = folder / "runs" / "check"

def pct(v, m): pass

for name, fn in (
    ("summary", extract_summary),
    ("video_structure", extract_video_structure),
    ("comprehension", extract_comprehension),
    ("landmarks", extract_landmarks),
):
    try:
        result = fn(folder, run, job["stages"], pct)
        result.pop("observations", None)
        print("=" * 30, name)
        print(json.dumps(result, ensure_ascii=False)[:1200])
    except Exception:
        print("=" * 30, name, "FAIL")
        traceback.print_exc()

print("SEARCH", json.dumps(search_job(job, "Тверской"), ensure_ascii=False)[:600])
