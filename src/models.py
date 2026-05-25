from __future__ import annotations

from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
