from __future__ import annotations

import argparse
import logging
import os
import tempfile

import numpy as np
import pyvista as pv

from src.api import (
    AUTH_URL_TEMPLATE,
    BASE_URL,
    CSV_URL_TEMPLATE,
    POINT_CLOUD_TYPE,
    POLYGON_TYPE,
    POLYGON_URL_TEMPLATE,
    fetch_csv,
    fetch_token,
)
from src.colormap import compute_displacement_colors, get_color
from src.mesh import ensure_mesh_in_s3, should_skip_processing
from src.s3 import get_s3_client, upload_to_s3

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

    mesh = ensure_mesh_in_s3(
        s3_client, bucket, resource_id, polygon_url, token, args.mesh
    )

    if should_skip_processing(s3_client, bucket, resource_id, csv_url, token):
        log.info("Output is up-to-date. Exiting.")
        return

    log.info("Fetching CSV data...")
    df = fetch_csv(csv_url, token)

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
