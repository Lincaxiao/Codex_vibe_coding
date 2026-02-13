from __future__ import annotations

import csv
from pathlib import Path

from .db import FocusLogDB


def export_sessions_csv(db: FocusLogDB, out_dir: Path) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    csv_path = out_path / "focuslog.csv"

    sessions = db.list_all_sessions()

    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "id",
                "start_time",
                "end_time",
                "duration_sec",
                "task",
                "tags",
                "kind",
                "completed",
                "interrupted_reason",
            ]
        )
        for item in sessions:
            writer.writerow(
                [
                    item.id,
                    item.start_time.isoformat(),
                    item.end_time.isoformat(),
                    item.duration_sec,
                    item.task,
                    item.tags,
                    item.kind,
                    1 if item.completed else 0,
                    item.interrupted_reason or "",
                ]
            )

    return csv_path
