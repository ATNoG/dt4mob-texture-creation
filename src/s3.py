from __future__ import annotations

from datetime import datetime
import logging

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from settings import settings

log = logging.getLogger(__name__)


def build_s3_client() -> BaseClient:
    if not all([settings.s3.endpoint, settings.s3.access_key, settings.s3.secret_key]):
        raise SystemExit(
            "Error: 's3.endpoint', 's3.access_key', and 's3.secret_key' must be set"
        )

    return boto3.client(
        "s3",
        endpoint_url=settings.s3.endpoint,
        aws_access_key_id=settings.s3.access_key,
        aws_secret_access_key=settings.s3.secret_key,
        verify=False,
    )


def get_s3_client() -> tuple[BaseClient, str]:
    bucket = settings.s3.bucket

    if not bucket:
        raise SystemExit("Error: 's3.bucket' is not set in config")

    s3_client = build_s3_client()

    try:
        s3_client.head_bucket(Bucket=bucket)
        log.info("S3 bucket is accessible")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "403" or "AccessDenied" in str(e):
            log.warning(
                "S3 Access Denied for bucket. Check credentials and permissions."
            )
        elif error_code == "404":
            log.warning("S3 bucket not found")
        else:
            log.warning("S3 connectivity check failed: %s", e)

    return s3_client, bucket


def download_from_s3(
    client: BaseClient, bucket: str, object_key: str, download_path: str
) -> None:
    try:
        client.download_file(bucket, object_key, download_path)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        log.error(
            "S3 download failed - Error code: %s, Message: %s",
            error_code,
            error_message,
        )
        raise


def upload_to_s3(
    client: BaseClient, file_path: str, bucket: str, object_key: str
) -> None:
    try:
        client.upload_file(file_path, bucket, object_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        log.error(
            "S3 upload failed - Error code: %s, Message: %s", error_code, error_message
        )
        raise


def upload_bytes_to_s3(
    client: BaseClient, data: bytes, bucket: str, object_key: str
) -> None:
    try:
        client.put_object(Bucket=bucket, Key=object_key, Body=data)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        log.error(
            "S3 upload failed - Error code: %s, Message: %s",
            error_code,
            error_message,
        )
        raise


def _get_s3_last_modified(
    client: BaseClient, bucket: str, object_key: str
) -> datetime | None:
    try:
        response = client.head_object(Bucket=bucket, Key=object_key)
        return response.get("LastModified")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "404":
            return None
        log.warning("Failed to HEAD S3 object /%s: %s", object_key, e)
        return None
