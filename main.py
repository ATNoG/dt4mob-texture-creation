import argparse
import logging
import os
import tempfile
from typing import cast

import boto3
import botocore
import httpx
import numpy as np
import pandas as pd
import pyvista as pv
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError
from pandas.io.common import StringIO
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BASE_URL = os.environ.get("BASE_URL")
AUTH_URL_TEMPLATE = "{base_url}/{tenant}/api/accounts/login"
CSV_URL_TEMPLATE = (
    "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
)
POLYGON_URL_TEMPLATE = (
    "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
)
POINT_CLOUD_TYPE = "ActivoGeotecnicoModeloModelType_CSV_Point_Cloud"
POLYGON_TYPE = "ActivoGeotecnicoModeloModelType_Ply"


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


def _build_s3_client() -> BaseClient:
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

    s3_client = _build_s3_client()

    # Test connectivity and permissions
    try:
        s3_client.head_bucket(Bucket=bucket)
        log.info("S3 bucket '%s' is accessible", bucket)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "403" or "AccessDenied" in str(e):
            log.warning(
                "S3 Access Denied for bucket '%s'. "
                "Check credentials and permissions.",
                bucket,
            )
        elif error_code == "404":
            log.warning("S3 bucket '%s' not found", bucket)
        else:
            log.warning("S3 connectivity check failed: %s", e)

    return cast(tuple[BaseClient, str], (s3_client, bucket))


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


def fetch_token(auth_url: str, username: str, password: str) -> str:
    request = AuthRequest(username=username, password=password)
    response = httpx.post(auth_url, json=request.model_dump())
    response.raise_for_status()
    data = response.json()
    auth_response = AuthResponse(**data)
    return auth_response.token


def fetch_polygon(polygon_url: str, token: str) -> bytes:
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(polygon_url, headers=headers)
    response.raise_for_status()
    return response.content


def fetch_csv(csv_url: str, token: str) -> pd.DataFrame:
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(csv_url, headers=headers)
    response.raise_for_status()
    content = response.text
    return pd.read_csv(StringIO(content))


def resolve_arg(args: argparse.Namespace, name: str) -> str:
    cli_value = getattr(args, name, None)
    env_value = os.environ.get(name.upper())
    if cli_value is not None:
        return cli_value
    if env_value is not None:
        return env_value
    raise SystemExit(
        f"Error: '{name}' must be provided via CLI argument or {name.upper()} env var"
    )


def get_color(flag: str) -> list[float]:
    f = str(flag).lower().strip()
    if "alert" in f:
        return [1.0, 1.0, 0.0]
    if "alarm" in f:
        return [1.0, 0.0, 0.0]
    return [0.0, 1.0, 0.0]


def compute_displacement_colors(dist_series: pd.Series) -> np.ndarray:
    """Compute RGB colors for displacement values from dist_3d_m field."""
    # Replace NaN with 0.0 (no displacement, green)
    dist = dist_series.fillna(0.0).to_numpy()
    # Clip to valid range of ±20mm (±0.02m)
    dist_clipped = np.clip(dist, -0.02, 0.02)
    # Initialize color array (N points × 3 RGB channels)
    colors = np.zeros((len(dist_clipped), 3))
    # Negative displacement: pink (1,0,1) → green (0,1,0)
    neg_mask = dist_clipped < 0
    if neg_mask.any():
        d_neg = dist_clipped[neg_mask]
        # Normalized position in negative range [0,1] where 0=-0.02m, 1=0m
        t_neg = (d_neg + 0.02) / 0.02
        colors[neg_mask, 0] = 1.0 - t_neg  # Red channel
        colors[neg_mask, 1] = t_neg  # Green channel
        colors[neg_mask, 2] = 1.0 - t_neg  # Blue channel
    # Positive displacement: green (0,1,0) → red (1,0,0)
    pos_mask = dist_clipped > 0
    if pos_mask.any():
        d_pos = dist_clipped[pos_mask]
        # Normalized position in positive range [0,1] where 0=0m, 1=0.02m
        t_pos = d_pos / 0.02
        colors[pos_mask, 0] = t_pos  # Red channel
        colors[pos_mask, 1] = 1.0 - t_pos  # Green channel
        colors[pos_mask, 2] = 0.0  # Blue channel
    # Zero/displacement-free points remain green (0,1,0)
    return colors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a textured mesh from a PLY file and fetched CSV data."
    )
    parser.add_argument(
        "--mesh",
        type=str,
        required=False,
        default=None,
        help="Path to the input PLY mesh file (optional, will attempt to fetch from API first)",
    )
    parser.add_argument("--tenant", type=str, required=False, help="Tenant identifier")
    parser.add_argument("--id", type=str, required=False, help="Resource ID")
    parser.add_argument("--username", type=str, required=False, help="Auth username")
    parser.add_argument("--password", type=str, required=False, help="Auth password")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tenant = resolve_arg(args, "tenant")
    resource_id = resolve_arg(args, "id")
    username = resolve_arg(args, "username")
    password = resolve_arg(args, "password")

    if BASE_URL is None:
        raise SystemExit("Error: 'BASE_URL' environment variable is not set")

    auth_url = AUTH_URL_TEMPLATE.format(tenant=tenant, base_url=BASE_URL)
    csv_url = CSV_URL_TEMPLATE.format(
        tenant=tenant, id=resource_id, modelType=POINT_CLOUD_TYPE, base_url=BASE_URL
    )
    polygon_url = POLYGON_URL_TEMPLATE.format(
        tenant=tenant, id=resource_id, modelType=POLYGON_TYPE, base_url=BASE_URL
    )

    log.info("Authenticating...")
    token = fetch_token(auth_url, username, password)

    log.info("Fetching CSV data...")
    df = fetch_csv(csv_url, token)

    log.info("Fetching mesh...")
    mesh = None
    try:
        polygon_bytes = fetch_polygon(polygon_url, token)
        with tempfile.NamedTemporaryFile(suffix=".ply", delete=True) as tmp_mesh:
            tmp_mesh.write(polygon_bytes)
            tmp_mesh.flush()
            mesh = pv.read(tmp_mesh.name)
            log.info("Mesh fetched from API")
    except httpx.HTTPError as e:
        log.warning("Failed to fetch mesh from API: %s", e)
        s3_input_bucket = os.environ.get("S3_INPUT_BUCKET")
        s3_input_key = os.environ.get("S3_INPUT_KEY")
        if s3_input_bucket and s3_input_key:
            try:
                s3_client = _build_s3_client()
                with tempfile.NamedTemporaryFile(suffix=".ply", delete=True) as tmp_mesh:
                    download_from_s3(s3_client, s3_input_bucket, s3_input_key, tmp_mesh.name)
                    mesh = pv.read(tmp_mesh.name)
                    log.info("Mesh fetched from S3: %s/%s", s3_input_bucket, s3_input_key)
            except ClientError as s3_err:
                log.error("Failed to download mesh from S3: %s", s3_err)
        if mesh is None and args.mesh is not None:
            log.info("Using local mesh file: %s", args.mesh)
            mesh = pv.read(args.mesh)
        if mesh is None:
            log.error("No mesh source available (API, S3, or local file). Exiting.")
            raise FileNotFoundError(
                "The mesh could not be fetched from the API, S3, or provided by the user"
            )

    log.info("Processing data...")
    # Alarmist texture (quality flag based)
    csv_colors = np.array([get_color(f) for f in df["Quality_flag"]])
    cloud = pv.PolyData(df[["X", "Y", "Z"]].values)
    cloud.point_data["Colors"] = csv_colors

    # Displacement texture
    disp_colors = compute_displacement_colors(df["dist_3d_m"])
    disp_cloud = pv.PolyData(df[["X", "Y", "Z"]].values)
    disp_cloud.point_data["Colors"] = disp_colors

    log.info("Interpolating...")
    if not isinstance(mesh, pv.PolyData):
        mesh = mesh.extract_surface()

    mesh.flip_faces(inplace=True)

    # Interpolate alarmist colors
    interpolated = mesh.interpolate(cloud, n_points=1, radius=0.5)
    interpolated.set_active_scalars("Colors")

    # Interpolate displacement colors
    disp_interpolated = mesh.interpolate(disp_cloud, n_points=1, radius=0.5)
    disp_interpolated.set_active_scalars("Colors")

    log.info("Exporting...")
    s3_client, bucket = get_s3_client()

    # Export alarmist texture
    with tempfile.NamedTemporaryFile(suffix=".gltf", delete=True) as tmp:
        tmp_path = tmp.name
        pl = pv.Plotter(off_screen=True)
        pl.add_mesh(interpolated, scalars="Colors", rgb=True, preference="point")
        pl.export_gltf(tmp_path)
        pl.close()

        object_key = f"{resource_id}_alarmist.gltf"
        upload_to_s3(s3_client, tmp_path, bucket, object_key)
        log.info("Successfully uploaded %s/%s to S3", bucket, object_key)

    # Export displacement texture
    with tempfile.NamedTemporaryFile(suffix=".gltf", delete=True) as tmp:
        tmp_path = tmp.name
        pl = pv.Plotter(off_screen=True)
        pl.add_mesh(disp_interpolated, scalars="Colors", rgb=True, preference="point")
        pl.export_gltf(tmp_path)
        pl.close()

        object_key = f"{resource_id}_displacement.gltf"
        upload_to_s3(s3_client, tmp_path, bucket, object_key)
        log.info("Successfully uploaded %s/%s to S3", bucket, object_key)


if __name__ == "__main__":
    main()
