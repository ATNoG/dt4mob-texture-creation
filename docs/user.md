# Mesh Texture Generator — User Guide

This program generates two textured 3D meshes (`.gltf` format) from a `.ply`
mesh and point cloud data fetched from an API. It produces one texture based on
quality flags (alarmist) and another based on displacement values.

## Configuration

The Texture Generator is configurable through a `config.toml` file at the
project root. Copy `config.toml.example` to `config.toml` and fill in the
values for your environment. Additionally, it can also be configured through
environment variables, which can be set on the shell or loaded from a .env
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

- `base_url`: The base URL of the API.

### `auth` Object

Contains the authentication credentials and resource identifiers.

- `tenant`: The tenant identifier for the API.
- `resource_id`: The resource ID of the asset to process.
- `username`: The username for API authentication.
- `password`: The password for API authentication.

### `s3` Object

Contains the connection settings for the S3-compatible storage used for both
input meshes and output textures.

- `endpoint`: The S3-compatible endpoint URL.
- `access_key`: The S3 access key.
- `secret_key`: The S3 secret key.
- `bucket`: The S3 bucket where both the input `.ply` and output `.gltf` files
  are stored.

### `mesh` Object

- `path`: Optional local file path to a PLY mesh file. If set, the program
  will load the mesh from this file and upload it to S3, skipping API and S3
  fallback retrieval.

## Environment Variable Overrides

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

## Run

The application was developed in a [uv](https://docs.astral.sh/uv) managed
environment. However, it is PEP 518 compliant, meaning that the `uv` tool is
not required to run the application, as the dependencies can be managed and
installed by using `pip` in a configured virtual environment, or `venv`.

Running the application is as simple as executing the
[main.py](../main.py) file in the managed environment:

```bash
# Using uv
uv run main.py

# Or using pip/venv in a PEP 518 compliant tool
python main.py
```

The `config.toml` configuration file must be placed in the root of the
project, which is the directory where `main.py` is located. The application
will automatically load that file and apply the configurations within it.

Additionally, given that this project uses `pydantic-settings`, the
configuration can also be set or overridden using environment variables. For
details on how to do this, refer to the `pydantic-settings` [official
documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## How it Works

The program follows a sequential pipeline:

### 1. Authentication

The program authenticates with the API using the credentials provided in the
`auth` section of the config. It calls the API's login endpoint at
`{base_url}/{tenant}/api/accounts/login` and receives a bearer token. This
token is used for all subsequent API requests.

### 2. Mesh Retrieval

The input PLY mesh is retrieved using the following priority order:

1. Local file — If `mesh.path` is set, the mesh is loaded directly from
   the local filesystem and uploaded to the S3 bucket as
   `{resource_id}.ply`.
2. API fetch — If no local path is set, the program tries to download the
   mesh from the API at
   `{base_url}/{tenant}/api/v1/activos-geotecnicos/{resource_id}/modelo/{POLYGON_TYPE}/download`.
   The downloaded mesh is cached in S3 for subsequent runs.
3. S3 fallback — If both local and API retrieval fail, the program will
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

Based on the `dist_3d_m` field with values clamped to ±20mm:

| dist_3d_m | Color | RGB |
|-----------|-------|-----|
| −20mm (max negative) | Pink | `(1.0, 0.0, 1.0)` |
| 0mm (none) | Green | `(0.0, 1.0, 0.0)` |
| +20mm (max positive) | Red | `(1.0, 0.0, 0.0)` |

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

Both files use vertex colors (RGB) embedded in the mesh data.

## Output Format

The output files are standard `.gltf` (GL Transmission Format) files containing
the original mesh geometry with per-vertex color data. They can be visualised
in any GLTF-compatible viewer (e.g., Babylon.js, Three.js, Windows 3D Viewer).
