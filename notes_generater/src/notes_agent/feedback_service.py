from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeedbackAppendResult:
    feedback_path: Path
    appended_items: list[str]
    section_title: str
    author: str | None
    appended_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_path": str(self.feedback_path),
            "appended_items": self.appended_items,
            "section_title": self.section_title,
            "author": self.author,
            "appended_at": self.appended_at,
        }


class FeedbackService:
    def append_feedback(
        self,
        *,
        notes_root: Path | str,
        items: list[str],
        section_title: str | None = None,
        author: str | None = None,
    ) -> FeedbackAppendResult:
        if not items:
            raise ValueError("feedback items cannot be empty")

        now = datetime.now(tz=timezone.utc).isoformat()
        notes = Path(notes_root).expanduser().resolve()
        feedback_path = notes / "review" / "feedback.md"
        feedback_path.parent.mkdir(parents=True, exist_ok=True)
        if not feedback_path.exists():
            feedback_path.write_text("# Final Review Feedback\n\n", encoding="utf-8")

        title = section_title or f"Feedback {now}"
        header = f"## {title}\n"
        meta = f"- Author: {author}\n" if author else ""
        checklist = "".join(f"- [ ] {item.strip()}\n" for item in items if item.strip())
        if not checklist:
            raise ValueError("all feedback items are empty")

        block = "\n" + header
        if meta:
            block += meta
        block += checklist
        block += f"- AddedAt: {now}\n"

        with feedback_path.open("a", encoding="utf-8") as fp:
            fp.write(block)

        return FeedbackAppendResult(
            feedback_path=feedback_path,
            appended_items=[item.strip() for item in items if item.strip()],
            section_title=title,
            author=author,
            appended_at=now,
        )
