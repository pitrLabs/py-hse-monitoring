"""
MinIO Object Storage Service
Handles file uploads, downloads, and presigned URL generation for media files.
"""
import io
import uuid
from datetime import datetime, timedelta
from typing import Optional, BinaryIO
import httpx
from minio import Minio
from minio.error import S3Error

from app.config import settings


class MinioStorageService:
    """Service for interacting with MinIO object storage."""

    def __init__(self):
        self.client: Optional[Minio] = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize MinIO client and create buckets if they don't exist."""
        if not settings.minio_enabled:
            print("[MinIO] MinIO is disabled in settings")
            return False

        try:
            self.client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )

            # Create buckets if they don't exist
            buckets = [
                settings.minio_bucket_alarm_images,
                settings.minio_bucket_recordings,
                settings.minio_bucket_local_videos,
            ]

            for bucket in buckets:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    print(f"[MinIO] Created bucket: {bucket}")
                else:
                    print(f"[MinIO] Bucket exists: {bucket}")

            self._initialized = True
            print("[MinIO] Initialized successfully")
            return True

        except Exception as e:
            print(f"[MinIO] Initialization failed: {e}")
            self._initialized = False
            return False

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self.client is not None

    def generate_object_name(self, prefix: str, extension: str) -> str:
        """Generate unique object path: YYYY/MM/DD/prefix_timestamp_uuid.ext"""
        now = datetime.utcnow()
        unique_id = uuid.uuid4().hex[:8]
        timestamp = now.strftime("%H%M%S")
        date_path = now.strftime("%Y/%m/%d")
        filename = f"{prefix}_{timestamp}_{unique_id}.{extension}"
        return f"{date_path}/{filename}"

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        file_data: BinaryIO,
        content_type: str = "application/octet-stream",
        file_size: int = -1
    ) -> Optional[str]:
        """
        Upload a file to MinIO.

        Args:
            bucket: Target bucket name
            object_name: Object path/name in the bucket
            file_data: File-like object or bytes
            content_type: MIME type of the file
            file_size: Size in bytes (-1 for unknown)

        Returns:
            Object name on success, None on failure
        """
        if not self.is_initialized:
            print("[MinIO] Not initialized")
            return None

        try:
            # If file_data is bytes, wrap in BytesIO
            if isinstance(file_data, bytes):
                file_data = io.BytesIO(file_data)
                file_size = len(file_data.getvalue())

            self.client.put_object(
                bucket,
                object_name,
                file_data,
                length=file_size,
                content_type=content_type
            )
            print(f"[MinIO] Uploaded: {bucket}/{object_name}")
            return object_name

        except S3Error as e:
            print(f"[MinIO] Upload error: {e}")
            return None

    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream"
    ) -> Optional[str]:
        """Upload bytes data to MinIO."""
        return self.upload_file(
            bucket,
            object_name,
            io.BytesIO(data),
            content_type,
            len(data)
        )

    async def upload_from_url(
        self,
        bucket: str,
        object_name: str,
        source_url: str,
        content_type: Optional[str] = None
    ) -> tuple[Optional[str], str]:
        """
        Download file from URL and upload to MinIO.
        Used for syncing media from BM-APP.

        Args:
            bucket: Target bucket
            object_name: Object path in bucket
            source_url: URL to download from
            content_type: MIME type (auto-detected if None)

        Returns:
            Tuple of (object_name or None, status)
            - ("path/to/file", "success") - upload succeeded
            - (None, "not_found") - file doesn't exist on source (404)
            - (None, "error") - other error occurred
        """
        if not self.is_initialized:
            print("[MinIO] Not initialized")
            return None, "error"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(source_url)

                # Handle 404 specifically - file doesn't exist
                if response.status_code == 404:
                    print(f"[MinIO] File not found (404): {source_url}")
                    return None, "not_found"

                response.raise_for_status()

                # Auto-detect content type if not provided
                if content_type is None:
                    content_type = response.headers.get("content-type", "application/octet-stream")

                data = response.content

                self.client.put_object(
                    bucket,
                    object_name,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=content_type
                )

                print(f"[MinIO] Uploaded from URL: {bucket}/{object_name}")
                return object_name, "success"

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"[MinIO] File not found (404): {source_url}")
                return None, "not_found"
            print(f"[MinIO] HTTP error downloading from {source_url}: {e}")
            return None, "error"
        except httpx.HTTPError as e:
            print(f"[MinIO] HTTP error downloading from {source_url}: {e}")
            return None, "error"
        except S3Error as e:
            print(f"[MinIO] Upload error: {e}")
            return None, "error"

    def get_presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: Optional[int] = None,
        response_headers: Optional[dict] = None
    ) -> Optional[str]:
        """
        Generate a presigned URL for downloading/viewing a file.

        Args:
            bucket: Bucket name
            object_name: Object path
            expires: URL expiry time in seconds (default from settings)
            response_headers: Optional headers to include (e.g., content-disposition for download)

        Returns:
            Presigned URL or None on failure
        """
        if not self.is_initialized:
            return None

        if expires is None:
            expires = settings.minio_presigned_url_expiry

        try:
            url = self.client.presigned_get_object(
                bucket,
                object_name,
                expires=timedelta(seconds=expires),
                response_headers=response_headers
            )
            return url
        except S3Error as e:
            print(f"[MinIO] Presigned URL error: {e}")
            return None

    def get_presigned_upload_url(
        self,
        bucket: str,
        object_name: str,
        expiry_seconds: Optional[int] = None
    ) -> Optional[str]:
        """
        Generate a presigned URL for direct browser upload.

        Args:
            bucket: Bucket name
            object_name: Object path where file will be uploaded
            expiry_seconds: URL expiry time

        Returns:
            Presigned upload URL or None on failure
        """
        if not self.is_initialized:
            return None

        if expiry_seconds is None:
            expiry_seconds = settings.minio_presigned_url_expiry

        try:
            url = self.client.presigned_put_object(
                bucket,
                object_name,
                expires=timedelta(seconds=expiry_seconds)
            )
            return url
        except S3Error as e:
            print(f"[MinIO] Presigned upload URL error: {e}")
            return None

    def delete_object(self, bucket: str, object_name: str) -> bool:
        """Delete an object from MinIO."""
        if not self.is_initialized:
            return False

        try:
            self.client.remove_object(bucket, object_name)
            print(f"[MinIO] Deleted: {bucket}/{object_name}")
            return True
        except S3Error as e:
            print(f"[MinIO] Delete error: {e}")
            return False

    def object_exists(self, bucket: str, object_name: str) -> bool:
        """Check if an object exists in the bucket."""
        if not self.is_initialized:
            return False

        try:
            self.client.stat_object(bucket, object_name)
            return True
        except S3Error:
            return False

    def get_object_info(self, bucket: str, object_name: str) -> Optional[dict]:
        """Get object metadata."""
        if not self.is_initialized:
            return None

        try:
            stat = self.client.stat_object(bucket, object_name)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "etag": stat.etag
            }
        except S3Error:
            return None

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        recursive: bool = True
    ) -> list:
        """List objects in a bucket with optional prefix filter."""
        if not self.is_initialized:
            return []

        try:
            objects = self.client.list_objects(bucket, prefix=prefix, recursive=recursive)
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified
                }
                for obj in objects
            ]
        except S3Error as e:
            print(f"[MinIO] List objects error: {e}")
            return []

    def get_bucket_stats(self, bucket: str) -> dict:
        """Get statistics for a bucket (count and total size)."""
        objects = self.list_objects(bucket)
        total_size = sum(obj.get("size", 0) for obj in objects)
        return {
            "object_count": len(objects),
            "total_size": total_size,
            "total_size_formatted": self._format_size(total_size)
        }

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    def health_check(self) -> dict:
        """Check MinIO connection health."""
        if not settings.minio_enabled:
            return {"status": "disabled", "message": "MinIO is disabled in settings"}

        if not self.is_initialized:
            return {"status": "error", "message": "MinIO client not initialized"}

        try:
            # Try to list buckets to verify connection
            buckets = list(self.client.list_buckets())
            return {
                "status": "healthy",
                "endpoint": settings.minio_endpoint,
                "buckets": [b.name for b in buckets]
            }
        except S3Error as e:
            return {"status": "error", "message": str(e)}


# ============ Global Instance ============

_storage_service: Optional[MinioStorageService] = None


def get_minio_storage() -> MinioStorageService:
    """Get the global MinIO storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = MinioStorageService()
    return _storage_service


def initialize_minio() -> bool:
    """Initialize the global MinIO storage service."""
    service = get_minio_storage()
    return service.initialize()
