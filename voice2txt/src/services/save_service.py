from pathlib import Path


class SaveServiceError(Exception):
    pass


class SaveService:
    def save_txt(self, text: str, target_path: Path) -> Path:
        if not target_path.suffix.lower() == ".txt":
            target_path = target_path.with_suffix(".txt")

        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            target_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise SaveServiceError(f"Failed to save transcript: {target_path}") from exc

        return target_path

