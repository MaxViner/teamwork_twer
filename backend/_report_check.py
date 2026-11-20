import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.jobs import load_job
from app.reporting import render_report
for jid in ("0cfa7047d77d428b9e1beb6616c484d6", "878322a91c8c437d97660b16a8606ada"):
    job = load_job(jid)
    text = render_report(job)
    out = Path("data") / jid / "report_check.md"
    out.write_text(text, encoding="utf-8")
    print(jid, len(text))
