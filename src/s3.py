from __future__ import annotations

from datetime import datetime
import logging
import os

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)


def build_s3_client() -> BaseClient:
    endpoint = os.environ.get("S3_ENDPOINT")
    access_key = os.environ.get("S3_ACCESS_KEY")
    secret_key = os.environ.get("S3_SECRET_KEY")

    for var, value in [
        ("S3_ENDPOINT", endpoint),
        ("S3_ACCESS_KEY", access_key),
        ("S3_SECRET_KEY", secret_key),
    ]:
        if value is None:
            raise SystemExit(f"Error: '{var}' environment variable is not set")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        verify=False,
    )


def get_s3_client() -> tuple[BaseClient, str]:
    bucket = os.environ.get("S3_BUCKET")

    if bucket is None:
        raise SystemExit("Error: 'S3_BUCKET' environment variable is not set")

    s3_client = build_s3_client()

    try:
        s3_client.head_bucket(Bucket=bucket)
        log.info("S3 bucket '%s' is accessible", bucket)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "403" or "AccessDenied" in str(e):
            log.warning(
                "S3 Access Denied for bucket '%s'. Check credentials and permissions.",
                bucket,
            )
        elif error_code == "404":
            log.warning("S3 bucket '%s' not found", bucket)
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
        log.error(
            "S3 Config - Endpoint: %s, Bucket: %s, File: %s, Key: %s",
            client.meta.endpoint_url,
            bucket,
            file_path,
            object_key,
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
        log.warning(
            "Failed to HEAD S3 object %s/%s: %s", bucket, object_key, e
        )
        return None
