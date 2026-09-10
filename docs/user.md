# Mesh Texture Generator

This program generates two textured 3D meshes (`.gltf` format) from a `.ply`
mesh and point cloud data fetched from an API. It produces one texture based on
quality flags (alarmist) and another based on displacement values.

## Prerequisites

Before using the Mesh Texture Generator, ensure you have:

| Requirement | Version/Details |
| ----------- | --------------- |
| Python | 3.12 or higher |
| S3-compatible storage | Accessible endpoint with a bucket for input meshes and output textures |
| API access | Reachable API with credentials for point cloud and mesh data |
| Python virtual environment | A configured virtual environment, either using `uv` or any other PEP-518 compliant system |

## Configuration

The Texture Generator is configurable through a `config.toml` file at the
project root. Copy `config.toml.example` to `config.toml` and fill in the
values for your environment. Additionally, it can also be configured through
environment variables, which can be set on the shell or loaded from a `.env`
file.

| Source | Priority |
|--------|----------|
| Environment variables | Highest |
| `.env` file | Medium |
| `config.toml` | Lowest (base config) |

Nested config values can be overridden via environment variables or a `.env`
file using `__` as a delimiter (such as `AUTH__TENANT=mycompany`).

The structure of `config.toml` is as follows:

- `api` (Object)
- `auth` (Object)
- `s3` (Object)
- `mesh` (Object)

### `api` Object

Contains the connection information for the API that provides the point cloud
and mesh data.

| Setting | Type | Description |
| ------- | ---- | ----------- |
| `base_url` | URL | The base URL of the API. |

### `auth` Object

Contains the authentication credentials and resource identifiers.

| Setting | Type | Description |
| ------- | ---- | ----------- |
| `tenant` | String | The tenant identifier for the API. |
| `resource_id` | String | The resource ID of the asset to process. |
| `username` | String | The username for API authentication. |
| `password` | String | The password for API authentication. |

### `s3` Object

Contains the connection settings for the S3-compatible storage used for both
input meshes and output textures.

| Setting | Type | Description |
| ------- | ---- | ----------- |
| `endpoint` | URL | The S3-compatible endpoint URL. |
| `access_key` | String | The S3 access key. |
| `secret_key` | String | The S3 secret key. |
| `bucket` | String | The S3 bucket where both the input `.ply` and output `.gltf` files are stored. |

### `mesh` Object

| Setting | Type | Default | Description |
| ------- | ---- | ------- | ----------- |
| `path` | Path | null | Optional local file path to a PLY mesh file. If set, the program will load the mesh from this file and upload it to S3, skipping API and S3 fallback retrieval. |

### Environment Variable Overrides

Nested fields can be overridden with `__` as the delimiter:

| Environment Variable | Config Path |
|---|---|
| `API__BASE_URL` | `api.base_url` |
| `AUTH__TENANT` | `auth.tenant` |
| `AUTH__RESOURCE_ID` | `auth.resource_id` |
| `AUTH__USERNAME` | `auth.username` |
| `AUTH__PASSWORD` | `auth.password` |
| `S3__ENDPOINT` | `s3.endpoint` |
| `S3__ACCESS_KEY` | `s3.access_key` |
| `S3__SECRET_KEY` | `s3.secret_key` |
| `S3__BUCKET` | `s3.bucket` |
| `MESH__PATH` | `mesh.path` |

## How it Works

The program follows a sequential pipeline:

### 1. Authentication

The program authenticates with the API using the credentials provided in the
`auth` section of the config. It calls the API's login endpoint at
`{base_url}/{tenant}/api/accounts/login` and receives a bearer token. This
token is used for all subsequent API requests.

### 2. Mesh Retrieval

The input PLY mesh is retrieved using the following priority order:

1. **Local file** — If `mesh.path` is set, the mesh is loaded directly from
   the local file system and uploaded to the S3 bucket as
   `{resource_id}.ply`.
2. **API fetch** — If no local path is set, the program tries to download the
   mesh from the API at
   `{base_url}/{tenant}/api/v1/activos-geotecnicos/{resource_id}/modelo/{POLYGON_TYPE}/download`.
   The downloaded mesh is cached in S3 for subsequent runs.
3. **S3 fallback** — If both local and API retrieval fail, the program will
   attempt to use an existing PLY previously cached in S3.

If no mesh can be obtained from any source, the program exits with an error.

### 3. Cache Check

Before processing, the program checks whether it can skip the work entirely. It
compares the `Last-Modified` timestamp of the API's CSV source with the
timestamps of the existing output `.gltf` files in the S3 bucket. If
the outputs are newer than or equal to the source, processing is skipped and
the program exits.

This allows the tool to be run idempotently, where repeated runs produce no work
unless the source data has changed. Additionally, this saves computation work.

### 4. Data Fetching

If processing is required, the program fetches a CSV file from the API at

```
{base_url}/{tenant}/api/v1/activos-geotecnicos/{resource_id}/modelo/{CSV_TYPE}/download
```

The CSV contains the following relevant columns:

- `X`, `Y`, `Z` — Spatial coordinates of each point
- `Quality_flag` — Quality classification (`alert`, `alarm`, `OK`)
- `dist_3d_m` — 3D displacement magnitude (signed, in meters)
- `dx_m`, `dy_m`, `dz_m` — Displacement components

### 5. Color Computation

Two color maps are computed in parallel:

#### Alarmist Texture

Based on the `Quality_flag` field:

| Flag | Color | RGB |
|------|-------|-----|
| `alert` | Yellow | `(1.0, 1.0, 0.0)` |
| `alarm` | Red | `(1.0, 0.0, 0.0)` |
| `OK` (default) | Green | `(0.0, 1.0, 0.0)` |

#### Displacement Texture

Based on the `dist_3d_m` field with values clamped to ±20 mm:

| dist_3d_m | Color | RGB |
|-----------|-------|-----|
| −20 mm (max negative) | Pink | `(1.0, 0.0, 1.0)` |
| 0 mm (none) | Green | `(0.0, 1.0, 0.0)` |
| +20 mm (max positive) | Red | `(1.0, 0.0, 0.0)` |

Values between these extremes are linearly interpolated, producing a smooth
gradient. Missing `dist_3d_m` values default to green (no displacement).

### 6. Interpolation

The colored point cloud is interpolated onto the mesh surface using pyvista's
`interpolate` method with a single nearest neighbor (`n_points=1`) and a search
radius of 0.5 meters. The mesh faces are flipped before interpolation to ensure
correct surface normals.

### 7. Export

Two `.gltf` files are generated and uploaded to the S3 bucket:

- `{resource_id}_alarmist.gltf` — Quality flag based texture
- `{resource_id}_displacement.gltf` — Displacement based texture

Both files use vertex colours (RGB) embedded in the mesh data.

## Output Format

The output files are standard `.gltf` (GL Transmission Format) files containing
the original mesh geometry with per-vertex color data. They can be visualized
in any GLTF-compatible viewer (e.g., Babylon.js, Three.js, Windows 3D Viewer).

## Deployment Guide

The texture creation pipeline is a Python application. However, it can be deployed in 3 different ways:
- Direct instantiation of the application
- Utilization of the provided Docker container
- Utilization of a Helm chart (for deployment in Kubernetes)

> **_NOTE:_** The provided application performs a single execution per
> invocation, given that it is intended to work as a periodic process. As such,
> the provided Helm chart is the recommended method for deployment, as it will
> automatically be configured as a Kubernetes CronJob. In the case of the other
> deployment methods, this behavior must be manually configured using other
> tools (such as native Linux cronjobs).

### Direct instantiation

The Python application was developed in a [uv](https://docs.astral.sh/uv)
managed environment. However, it is PEP-518 compliant, meaning that the `uv`
tool is not required to run the application, as the dependencies can be managed
and installed by using `pip` in a configured virtual environment, or `venv`.

Using direct instantiation is as simple as running the [main.py](../main.py)
file in the managed environment:

```bash
# Using uv
uv run main.py

# Or using pip/venv in a PEP 518 compliant tool
python main.py
```

In this case, the `config.toml` configuration file must be placed in the root
of the project, which is the directory where the `main.py` file is located. The
application will automatically load that file and apply the configurations
within it. For details on how to configure the Texture Generator, refer to the
[Configuration](#configuration) section. Additionally, given that this project
utilizes `pydantic-settings`, these can also be set using environment variables.
These are named just like the fields, using a double underscore (`__`) for
nested objects. For example, the S3 object's `endpoint` is defined as
`S3__ENDPOINT`. Refer to the [Environment Variable Overrides](#environment-variable-overrides) table
for the full list.

### Docker

The usage of the Docker file is simpler than the direct instantiation, as the
image only needs to be built (or use the pre-built image in
`atnog-harbor.av.it.pt/dt4mob/texture-creation`).

```bash
docker build -t texture-creation .
# Or use the pre-built image:
docker run atnog-harbor.av.it.pt/dt4mob/texture-creation
```

The `config.toml` and any other required files must be mounted into the
container at the paths configured in `config.toml`. These paths MUST match the
paths inside the container, not those of the host.

```bash
docker run -v /path/to/config.toml:/app/config.toml atnog-harbor.av.it.pt/dt4mob/texture-creation
```

> **_NOTE:_** This will perform a single execution of the Texture Generator.
> The periodic execution behavior is left for implementation by the
> administrator.

### Helm Chart

The Helm chart is available at the [dt4mob-platform GitHub
repository](https://github.com/ATNoG/dt4mob-platform) and can be installed
using the Helm installer:

```bash
helm install texture-creation <path_to_chart> -f <path_to_values.yml>
```

The configuration is done via the `values.yml` file, but follows the same
structure of the `config.toml` configuration file.
