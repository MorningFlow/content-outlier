import shutil
from pathlib import Path
from typing import Optional
from app.storage.base import BaseStorage
from app.config import settings


class LocalStorage(BaseStorage):
    """Local VPS filesystem storage implementation."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.LOCAL_STORAGE_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _full_path(self, relative_path: str) -> Path:
        clean = relative_path.lstrip("/\\")
        return self.base_dir / clean

    def save_bytes(self, data: bytes, relative_path: str, content_type: Optional[str] = None) -> str:
        target = self._full_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return relative_path.replace("\\", "/")

    def save_file(self, local_source_path: Path, relative_path: str, content_type: Optional[str] = None) -> str:
        target = self._full_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_source_path, target)
        return relative_path.replace("\\", "/")

    def get_url(self, relative_path: str) -> str:
        clean = relative_path.lstrip("/\\").replace("\\", "/")
        return f"/media/{clean}"

    def exists(self, relative_path: str) -> bool:
        return self._full_path(relative_path).is_file()

    def delete(self, relative_path: str) -> bool:
        target = self._full_path(relative_path)
        if target.is_file():
            target.unlink()
            return True
        return False
