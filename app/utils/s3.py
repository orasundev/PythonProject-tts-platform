"""
S3-compatible object storage helpers (AWS S3, MinIO, Cloudflare R2).
"""

import io
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from loguru import logger

from app.config import get_settings

settings = get_settings()


def _get_client():
    kwargs = {
        "aws_access_key_id": settings.aws_access_key_id or None,
        "aws_secret_access_key": settings.aws_secret_access_key or None,
        "region_name": settings.aws_region,
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def build_s3_key(org_id: uuid.UUID, file_id: uuid.UUID, fmt: str = "mp3") -> str:
    now = datetime.now(timezone.utc)
    return f"{org_id}/{now.year}/{now.month:02d}/{file_id}.{fmt}"


def upload_audio(data: bytes, s3_key: str, content_type: str = "audio/mpeg") -> None:
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
    logger.info(f"Uploaded {len(data)} bytes to s3://{settings.s3_bucket}/{s3_key}")


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )


def delete_object(s3_key: str) -> None:
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.s3_bucket, Key=s3_key)
        logger.info(f"Deleted s3://{settings.s3_bucket}/{s3_key}")
    except ClientError as exc:
        logger.warning(f"Failed to delete {s3_key}: {exc}")


def check_bucket_accessible() -> bool:
    """Health check — returns True if the bucket is reachable."""
    try:
        client = _get_client()
        client.head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False


CONTENT_TYPE_MAP = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
}
