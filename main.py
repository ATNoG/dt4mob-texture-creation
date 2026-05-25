from __future__ import annotations

import argparse
import logging
import os
import tempfile

import httpx
import numpy as np
import pyvista as pv
from botocore.client import BaseClient

from src.api import _get_api_last_modified, fetch_csv, fetch_polygon, fetch_token
from src.colormap import compute_displacement_colors, get_color
from src.config import (
    AUTH_URL_TEMPLATE,
    BASE_URL,
    CSV_URL_TEMPLATE,
    POINT_CLOUD_TYPE,
    POLYGON_TYPE,
    POLYGON_URL_TEMPLATE,
)
from src.s3 import (
    _get_s3_last_modified,
    build_s3_client,
    download_from_s3,
    get_s3_client,
    upload_to_s3,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


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


def should_skip_processing(
    s3_client: BaseClient,
    bucket: str,
    resource_id: str,
    csv_url: str,
    token: str,
) -> bool:
    alarmist_key = f"{resource_id}_alarmist.gltf"
    displacement_key = f"{resource_id}_displacement.gltf"

    alarmist_lm = _get_s3_last_modified(s3_client, bucket, alarmist_key)
    displacement_lm = _get_s3_last_modified(s3_client, bucket, displacement_key)

    if alarmist_lm is None or displacement_lm is None:
        log.info("S3 output file(s) not found, proceeding with processing")
        return False

    s3_lastmodified = alarmist_lm if alarmist_lm < displacement_lm else displacement_lm

    api_last_modified = _get_api_last_modified(csv_url, token)
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

    s3_client, bucket = get_s3_client()

    if should_skip_processing(s3_client, bucket, resource_id, csv_url, token):
        log.info("Output is up-to-date. Exiting.")
        return

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
                s3_client = build_s3_client()
                with tempfile.NamedTemporaryFile(
                    suffix=".ply", delete=True
                ) as tmp_mesh:
                    download_from_s3(
                        s3_client, s3_input_bucket, s3_input_key, tmp_mesh.name
                    )
                    mesh = pv.read(tmp_mesh.name)
                    log.info("Mesh fetched from S3")
            except Exception as s3_err:
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
    csv_colors = np.array([get_color(f) for f in df["Quality_flag"]])
    cloud = pv.PolyData(df[["X", "Y", "Z"]].values)
    cloud.point_data["Colors"] = csv_colors

    disp_colors = compute_displacement_colors(df["dist_3d_m"])
    disp_cloud = pv.PolyData(df[["X", "Y", "Z"]].values)
    disp_cloud.point_data["Colors"] = disp_colors

    log.info("Interpolating...")
    if not isinstance(mesh, pv.PolyData):
        mesh = mesh.extract_surface()

    mesh.flip_faces(inplace=True)

    interpolated = mesh.interpolate(cloud, n_points=1, radius=0.5)
    interpolated.set_active_scalars("Colors")

    disp_interpolated = mesh.interpolate(disp_cloud, n_points=1, radius=0.5)
    disp_interpolated.set_active_scalars("Colors")

    log.info("Exporting...")

    with tempfile.NamedTemporaryFile(suffix=".gltf", delete=True) as tmp:
        tmp_path = tmp.name
        pl = pv.Plotter(off_screen=True)
        pl.add_mesh(interpolated, scalars="Colors", rgb=True, preference="point")
        pl.export_gltf(tmp_path)
        pl.close()

        object_key = f"{resource_id}_alarmist.gltf"
        upload_to_s3(s3_client, tmp_path, bucket, object_key)
        log.info("Successfully uploaded /%s to S3", object_key)

    with tempfile.NamedTemporaryFile(suffix=".gltf", delete=True) as tmp:
        tmp_path = tmp.name
        pl = pv.Plotter(off_screen=True)
        pl.add_mesh(disp_interpolated, scalars="Colors", rgb=True, preference="point")
        pl.export_gltf(tmp_path)
        pl.close()

        object_key = f"{resource_id}_displacement.gltf"
        upload_to_s3(s3_client, tmp_path, bucket, object_key)
        log.info("Successfully uploaded /%s to S3", object_key)


if __name__ == "__main__":
    main()
