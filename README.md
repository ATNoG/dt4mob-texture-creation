# Mesh Texture Generator

This project provides a Python-based command-line tool that generates textured 3D meshes
(`.gltf` format) from a `.ply` mesh and point cloud data fetched from an API.

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

4. **Mesh Processing** - Loads the target mesh, first attempting to retrieve it
   from the WebAPI, and if that fails, from the PLY file stored in the S3
   bucket provided. Then extracts the surface geometry, and interpolates colors
   from the CSV point cloud onto the mesh.

5. **Export** - Renders and exports both textured meshes as `.gltf` files.

## Configuration

This section can be found in the [user guide](./docs/user.md)


## Deployment

This section can be found in the [administration guide](./docs/admin.md)
