from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import logging
import os

import httpx
import pandas as pd
from pandas.io.common import StringIO
from pydantic import BaseModel

log = logging.getLogger(__name__)

# URL configuration
BASE_URL = os.environ.get("BASE_URL")
AUTH_URL_TEMPLATE = "{base_url}/{tenant}/api/accounts/login"
CSV_URL_TEMPLATE = "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
POLYGON_URL_TEMPLATE = "{base_url}/{tenant}/api/v1/activos-geotecnicos/{id}/modelo/{modelType}/download"
POINT_CLOUD_TYPE = "ActivoGeotecnicoModeloModelType_CSV_Point_Cloud"
POLYGON_TYPE = "ActivoGeotecnicoModeloModelType_Ply"


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


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


def _get_api_last_modified(url: str, token: str) -> datetime | None:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = httpx.head(url, headers=headers)
        response.raise_for_status()
        last_modified = response.headers.get("Last-Modified")
        if last_modified is None:
            return None
        return parsedate_to_datetime(last_modified)
    except httpx.HTTPError as e:
        log.warning("Failed to HEAD API: %s", e)
        return None
