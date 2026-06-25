from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import logging

import httpx
import pandas as pd
from pandas.io.common import StringIO
from pydantic import BaseModel

from settings import settings

log = logging.getLogger(__name__)

POINT_CLOUD_TYPE = "ActivoGeotecnicoModeloModelType_CSV_Point_Cloud"
POLYGON_TYPE = "ActivoGeotecnicoModeloModelType_Ply"


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


def polygon_url() -> str:
    return (
        f"{settings.api.base_url}/{settings.auth.tenant}"
        f"/api/v1/activos-geotecnicos/{settings.auth.resource_id}"
        f"/modelo/{POLYGON_TYPE}/download"
    )


def csv_url() -> str:
    return (
        f"{settings.api.base_url}/{settings.auth.tenant}"
        f"/api/v1/activos-geotecnicos/{settings.auth.resource_id}"
        f"/modelo/{POINT_CLOUD_TYPE}/download"
    )


def _auth_url() -> str:
    return f"{settings.api.base_url}/{settings.auth.tenant}/api/accounts/login"


def fetch_token() -> str:
    url = _auth_url()
    request = AuthRequest(
        username=settings.auth.username, password=settings.auth.password
    )
    response = httpx.post(url, json=request.model_dump())
    response.raise_for_status()
    data = response.json()
    auth_response = AuthResponse(**data)
    return auth_response.token


def fetch_polygon(token: str) -> bytes:
    url = polygon_url()
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    return response.content


def fetch_csv(token: str) -> pd.DataFrame:
    url = csv_url()
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, headers=headers)
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
