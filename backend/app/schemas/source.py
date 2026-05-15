from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataSourceCreate(BaseModel):
    country: str
    source_name: str = Field(min_length=1, max_length=100)
    supported_fields: list[str] = Field(default_factory=list)
    config: dict | None = None
    critical_fields: list[str] | None = None


class DataSourceUpdate(BaseModel):
    source_name: str | None = Field(default=None, min_length=1, max_length=100)
    supported_fields: list[str] | None = None
    config: dict | None = None
    critical_fields: list[str] | None = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country: str
    source_name: str
    supported_fields: list[str] | None
    config: dict | None
    critical_fields: list[str] | None


class DataSourceListItem(BaseModel):
    id: str
    name: str
    country: str | None = None
    supported_fields: list[str] | None
    source_role: str | None = None
    trust_level: str | None = None
    config: dict | None = None
    critical_fields: list[str] | None = None


class DataSourceListResponse(BaseModel):
    sources: list[DataSourceListItem]


class SourceCountryListResponse(BaseModel):
    countries: list[str]
