from __future__ import annotations

import logging
import tempfile

import httpx
import pyvista as pv
from botocore.client import BaseClient

from settings import settings
from src.api import _get_api_last_modified, csv_url, fetch_polygon, polygon_url
from src.s3 import _get_s3_last_modified, download_from_s3, upload_bytes_to_s3

log = logging.getLogger(__name__)


def ensure_mesh_in_s3(
    s3_client: BaseClient,
    bucket: str,
    token: str,
    mesh_path: str | None = None,
) -> pv.DataObject:
    resource_id = settings.auth.resource_id
    ply_key = f"{resource_id}.ply"

    if mesh_path is not None:
        log.info("Loading mesh from local file: %s", mesh_path)
        mesh = pv.read(mesh_path)
        with open(mesh_path, "rb") as f:
            upload_bytes_to_s3(s3_client, f.read(), bucket, ply_key)
        log.info("Uploaded local mesh to S3 as %s", ply_key)
        return mesh

    s3_ply_lm = _get_s3_last_modified(s3_client, bucket, ply_key)

    polygon_api_lm = _get_api_last_modified(polygon_url(), token)

    if s3_ply_lm is None and polygon_api_lm is None:
        raise FileNotFoundError(
            "No PLY file in S3 and API is unreachable. Cannot proceed."
        )

    need_api_fetch = s3_ply_lm is None or (
        polygon_api_lm is not None and polygon_api_lm > s3_ply_lm
    )

    if need_api_fetch:
        try:
            log.info("Fetching mesh from API...")
            polygon_bytes = fetch_polygon(token)
            upload_bytes_to_s3(s3_client, polygon_bytes, bucket, ply_key)
            log.info("Uploaded mesh from API to S3 as %s", ply_key)
            with tempfile.NamedTemporaryFile(suffix=".ply", delete=True) as tmp:
                tmp.write(polygon_bytes)
                tmp.flush()
                return pv.read(tmp.name)
        except httpx.HTTPError as e:
            log.warning("Failed to fetch mesh from API: %s", e)
            if s3_ply_lm is not None:
                log.info("Falling back to existing PLY in S3")
            else:
                raise FileNotFoundError(
                    "Failed to fetch PLY from API and no S3 fallback available."
                ) from e

    log.info("Using PLY from S3: %s", ply_key)
    with tempfile.NamedTemporaryFile(suffix=".ply", delete=True) as tmp:
        download_from_s3(s3_client, bucket, ply_key, tmp.name)
        return pv.read(tmp.name)


def should_skip_processing(
    s3_client: BaseClient,
    bucket: str,
    token: str,
) -> bool:
    resource_id = settings.auth.resource_id
    ply_key = f"{resource_id}.ply"
    if _get_s3_last_modified(s3_client, bucket, ply_key) is None:
        raise FileNotFoundError(
            f"PLY file '{ply_key}' not found in S3 bucket '{bucket}'."
        )

    alarmist_key = f"{resource_id}_alarmist.gltf"
    displacement_key = f"{resource_id}_displacement.gltf"

    alarmist_lm = _get_s3_last_modified(s3_client, bucket, alarmist_key)
    displacement_lm = _get_s3_last_modified(s3_client, bucket, displacement_key)

    if alarmist_lm is None or displacement_lm is None:
        log.info("S3 output file(s) not found, proceeding with processing")
        return False

    s3_lastmodified = alarmist_lm if alarmist_lm < displacement_lm else displacement_lm

    api_last_modified = _get_api_last_modified(csv_url(), token)
    if api_last_modified is None:
        log.info("Could not determine API Last-Modified, proceeding with processing")
        return False

    log.info(
        "S3 output last modified: %s, API source last modified: %s",
        s3_lastmodified,
        api_last_modified,
    )

    if s3_lastmodified >= api_last_modified:
        log.info("S3 output is up-to-date, skipping processing")
        return True

    log.info("S3 output is stale, proceeding with processing")
    return False
