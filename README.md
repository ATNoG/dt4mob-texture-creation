# Mesh Texture Generator

This project provides a Python-based command-line tool that generates textured 3D meshes
(`.gltf` format) from a `.ply` mesh file and point cloud data fetched from an API.

The tool generates **two textures** for every mesh:
1. **Alarmist Texture** - Colorizes the mesh based on quality flags (alert/alarm/OK)
2. **Displacement Texture** - Colorizes the mesh based on displacement values from the point cloud

## How it Works

The tool performs the following steps:

1. **Authentication** - Authenticates with the API using username/password credentials
   to obtain a bearer token.

2. **Data Fetching** - Fetches CSV data from the API using the bearer token. The CSV
   contains spatial coordinates (`X`, `Y`, `Z`), `Quality_flag`, and displacement
   values (`dx_m`, `dy_m`, `dz_m`, `dist_3d_m`) for each point.

3. **Texture Generation** - Creates two textures:

   ### Alarmist Texture (`_alarmist.gltf`)
   Based on the `Quality_flag` field:
   - `alert`: Yellow `(1.0, 1.0, 0.0)`
   - `alarm`: Red `(1.0, 0.0, 0.0)`
   - `OK` (default): Green `(0.0, 1.0, 0.0)`

   ### Displacement Texture (`_displacement.gltf`)
   Based on the `dist_3d_m` field (displacement magnitude with sign):
   - Range: `-0.02m` to `+0.02m` (±20mm)
   - `-0.02m` (max negative): Pink `(1.0, 0.0, 1.0)`
   - `0.0m` (no displacement): Green `(0.0, 1.0, 0.0)`
   - `+0.02m` (max positive): Red `(1.0, 0.0, 0.0)`
   - Smooth gradient between these values (5mm intervals)
   - Missing `dist_3d_m` values default to green (no displacement)

4. **Mesh Processing** - Loads the target mesh from the PLY file, extracts the
   surface geometry, and interpolates colors from the CSV point cloud onto the mesh.

5. **Export** - Renders and exports both textured meshes as `.gltf` files.

## Prerequisites

This project uses [uv](https://github.com/astral-sh/uv) to manage its dependencies and
Python environment.

First, install `uv` on your system. Then, from the root of the project, install the
dependencies by running:

```bash
uv sync
```

Then, after installing/updating the dependencies, the program can be executed by running:

```bash
uv run main.py
```

## CLI Usage

The tool requires a `--mesh` argument, and all other parameters can be provided either
via CLI arguments or environment variables.

```bash
uv run main.py --mesh <path_to_ply> --tenant <tenant> --id <id> --username <username> --password <password>
```

### Arguments

| Argument    | Description                   | Required | Environment Variable |
|-------------|-------------------------------|----------|----------------------|
| `--mesh`    | Path to the input PLY file    | Yes      | -                    |
| `--tenant`  | Tenant identifier             | Yes      | `TENANT`             |
| `--id`      | Resource ID                   | Yes      | `ID`                 |
| `--username`| Authentication username        | Yes      | `USERNAME`           |
| `--password`| Authentication password        | Yes      | `PASSWORD`           |

Priority: CLI argument > environment variable

### Example

```bash
uv run main.py \
  --mesh ./meshes/model.ply \
  --tenant mycompany \
  --id 12345 \
  --username admin \
  --password secret
```

Or using environment variables:

```bash
export TENANT=mycompany
export ID=12345
export USERNAME=admin
export PASSWORD=secret

uv run main.py --mesh ./meshes/model.ply --tenant mycompany
```

The output files will be saved to your S3 bucket as:
- `{resource_id}_alarmist.gltf` - Quality flag based texture
- `{resource_id}_displacement.gltf` - Displacement based texture