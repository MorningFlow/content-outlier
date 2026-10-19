from app.config import settings
from app.storage.base import BaseStorage
from app.storage.local import LocalStorage


_storage_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        if settings.STORAGE_BACKEND.lower() == "s3":
            from app.storage.s3 import S3Storage
            _storage_instance = S3Storage()
        else:
            _storage_instance = LocalStorage()
    return _storage_instance


__all__ = ["BaseStorage", "LocalStorage", "get_storage"]
