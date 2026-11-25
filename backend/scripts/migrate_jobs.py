"""CLI миграции job.json на консолидированные этапы.

Примеры:
    python scripts/migrate_jobs.py --dry-run
    python scripts/migrate_jobs.py
    python scripts/migrate_jobs.py --data-dir D:\\path\\to\\data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.migrationService.jobs import migrate_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Миграция job.json на visual_analysis, place_profile и location_prompt.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Каталог с папками заданий (по умолчанию backend/data).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет изменено.",
    )
    args = parser.parse_args()

    summary = migrate_all(args.data_dir, dry_run=args.dry_run)

    print(json.dumps({
        **summary,
        "dry_run": bool(args.dry_run),
    }, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
