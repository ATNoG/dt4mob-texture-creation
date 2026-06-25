from __future__ import annotations

import logging
import tempfile

import numpy as np
import pyvista as pv

from settings import settings
from src.api import fetch_csv, fetch_token
from src.colormap import compute_displacement_colors, get_color
from src.mesh import ensure_mesh_in_s3, should_skip_processing
from src.s3 import get_s3_client, upload_to_s3

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    resource_id = settings.auth.resource_id
    mesh_path = settings.mesh.path or None

    log.info("Authenticating...")
    token = fetch_token()

    s3_client, bucket = get_s3_client()

    mesh = ensure_mesh_in_s3(s3_client, bucket, token, mesh_path)

    if should_skip_processing(s3_client, bucket, token):
        log.info("Output is up-to-date. Exiting.")
        return

    log.info("Fetching CSV data...")
    df = fetch_csv(token)

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
