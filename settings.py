from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class S3Settings(BaseModel):
    endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost")
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""


class ApiSettings(BaseModel):
    base_url: AnyHttpUrl = AnyHttpUrl("http://localhost")


class AuthSettings(BaseModel):
    tenant: str = ""
    resource_id: str = ""
    username: str = ""
    password: str = ""


class MeshSettings(BaseModel):
    path: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file="config.toml",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    s3: S3Settings = S3Settings()
    api: ApiSettings = ApiSettings()
    auth: AuthSettings = AuthSettings()
    mesh: MeshSettings = MeshSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            TomlConfigSettingsSource(settings_cls),
            DotEnvSettingsSource(settings_cls),
            EnvSettingsSource(settings_cls),
        )


settings = Settings()
