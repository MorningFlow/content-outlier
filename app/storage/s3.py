from pathlib import Path
from typing import Optional
import logging
from app.storage.base import BaseStorage
from app.config import settings

logger = logging.getLogger(__name__)


class S3Storage(BaseStorage):
    """S3-compatible / Cloudflare R2 object storage provider."""

    def __init__(self):
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.region = settings.S3_REGION_NAME
        self.public_base_url = settings.S3_PUBLIC_BASE_URL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3  # Optional lazy import
                self._client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                    region_name=self.region,
                )
            except ImportError:
                raise RuntimeError("boto3 is required for S3/R2 storage. Run: pip install boto3")
        return self._client

    def save_bytes(self, data: bytes, relative_path: str, content_type: Optional[str] = None) -> str:
        client = self._get_client()
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        clean_key = relative_path.lstrip("/\\").replace("\\", "/")
        client.put_object(Bucket=self.bucket, Key=clean_key, Body=data, **extra_args)
        return clean_key

    def save_file(self, local_source_path: Path, relative_path: str, content_type: Optional[str] = None) -> str:
        client = self._get_client()
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        clean_key = relative_path.lstrip("/\\").replace("\\", "/")
        client.upload_file(str(local_source_path), self.bucket, clean_key, ExtraArgs=extra_args or None)
        return clean_key

    def get_url(self, relative_path: str) -> str:
        clean_key = relative_path.lstrip("/\\").replace("\\", "/")
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{clean_key}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{clean_key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{clean_key}"

    def exists(self, relative_path: str) -> bool:
        client = self._get_client()
        clean_key = relative_path.lstrip("/\\").replace("\\", "/")
        try:
            client.head_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception:
            return False

    def delete(self, relative_path: str) -> bool:
        client = self._get_client()
        clean_key = relative_path.lstrip("/\\").replace("\\", "/")
        try:
            client.delete_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete S3 object {clean_key}: {e}")
            return False
