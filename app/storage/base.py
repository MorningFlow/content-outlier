from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseStorage(ABC):
    """Abstract interface for video & thumbnail media storage."""

    @abstractmethod
    def save_bytes(self, data: bytes, relative_path: str, content_type: Optional[str] = None) -> str:
        """Saves binary data and returns the stored relative key/path."""
        pass

    @abstractmethod
    def save_file(self, local_source_path: Path, relative_path: str, content_type: Optional[str] = None) -> str:
        """Copies/uploads an existing local file to storage and returns relative path."""
        pass

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """Returns public or API accessible URL for the media asset."""
        pass

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """Checks if file exists in storage."""
        pass

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """Deletes media asset from storage."""
        pass
