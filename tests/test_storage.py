import tempfile
from pathlib import Path
from app.storage.local import LocalStorage


def test_local_storage_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalStorage(base_dir=tmp_dir)

        # 1. Save bytes
        data = b"sample video mp4 content"
        key = storage.save_bytes(data, "videos/user/reel1.mp4", content_type="video/mp4")
        assert key == "videos/user/reel1.mp4"
        assert storage.exists(key) is True

        # 2. URL generation
        url = storage.get_url(key)
        assert url == "/media/videos/user/reel1.mp4"

        # 3. Deletion
        assert storage.delete(key) is True
        assert storage.exists(key) is False
