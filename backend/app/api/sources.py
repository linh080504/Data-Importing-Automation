from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.data_source import DataSource
from app.schemas.source import (
    DataSourceCreate,
    DataSourceListItem,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    SourceCountryListResponse,
)
from app.services.source_registry import recommended_sources_for_country

router = APIRouter(prefix="/sources", tags=["sources"])

_GLOBAL_SOURCE_COUNTRY = "*"
_DEFAULT_COUNTRIES = [
    "Australia",
    "Canada",
    "Germany",
    "Japan",
    "Singapore",
    "United Kingdom",
    "USA",
    "Vietnam",
]


def _matches_country(source: DataSource, country: str | None) -> bool:
    if not country:
        return True
    source_country = (source.country or "").strip()
    if source_country == country:
        return True
    return source_country == _GLOBAL_SOURCE_COUNTRY


@router.get("/countries", response_model=SourceCountryListResponse)
def list_source_countries(db: Session = Depends(get_db)) -> SourceCountryListResponse:
    sources = db.query(DataSource).order_by(DataSource.country.asc(), DataSource.source_name.asc()).all()
    discovered = {source.country.strip() for source in sources if (source.country or "").strip() and source.country.strip() != _GLOBAL_SOURCE_COUNTRY}
    countries = sorted(discovered.union(_DEFAULT_COUNTRIES))
    return SourceCountryListResponse(countries=countries)


@router.get("/recommended")
def list_recommended_sources(country: str = Query(..., min_length=1)) -> dict[str, object]:
    requested_country = country.strip()
    return {
        "country": requested_country,
        "templates": recommended_sources_for_country(requested_country),
    }


@router.get("", response_model=DataSourceListResponse)
def list_sources(
    country: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DataSourceListResponse:
    requested_country = country.strip() if country else None
    sources = db.query(DataSource).order_by(DataSource.source_name.asc()).all()
    filtered_sources = [source for source in sources if _matches_country(source, requested_country)]
    return DataSourceListResponse(
        sources=[
            DataSourceListItem(
                id=str(source.id),
                name=source.source_name,
                country=requested_country if source.country == _GLOBAL_SOURCE_COUNTRY and requested_country else source.country,
                supported_fields=source.supported_fields,
                source_role=(source.config or {}).get("role"),
                trust_level=(source.config or {}).get("trust_level"),
                config=source.config,
                critical_fields=source.critical_fields,
            )
            for source in filtered_sources
        ]
    )


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: DataSourceCreate, db: Session = Depends(get_db)) -> DataSourceResponse:
    source = DataSource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return DataSourceResponse.model_validate(source)


@router.put("/{source_id}", response_model=DataSourceResponse)
def update_source(
    source_id: str,
    payload: DataSourceUpdate,
    db: Session = Depends(get_db),
) -> DataSourceResponse:
    source = db.query(DataSource).filter(DataSource.id == source_id).one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "config" and isinstance(value, dict):
            source.config = {**(source.config or {}), **value}
        else:
            setattr(source, key, value)

    db.add(source)
    db.commit()
    db.refresh(source)
    return DataSourceResponse.model_validate(source)
