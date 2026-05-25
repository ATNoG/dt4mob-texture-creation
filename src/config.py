from __future__ import annotations

import os

BASE_URL = os.environ.get("BASE_URL")
AUTH_URL_TEMPLATE = "{base_url}/{tenant}/api/accounts/login"
CSV_URL_TEMPLATE = "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
POLYGON_URL_TEMPLATE = "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
POINT_CLOUD_TYPE = "ActivoGeotecnicoModeloModelType_CSV_Point_Cloud"
POLYGON_TYPE = "ActivoGeotecnicoModeloModelType_Ply"
