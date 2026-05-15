from fastapi import APIRouter

from app.api.compare import router as compare_router
from app.api.crawl_jobs import router as crawl_jobs_router
from app.api.export import router as export_router
from app.api.fields import router as fields_router
from app.api.health import router as health_router
from app.api.internal import router as internal_router
from app.api.import_api import router as import_router
from app.api.import_readiness import router as import_readiness_router
from app.api.review import router as review_router
from app.api.review_actions import router as review_actions_router
from app.api.sources import router as sources_router
from app.api.templates import router as templates_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(templates_router)
api_router.include_router(fields_router)
api_router.include_router(sources_router)
api_router.include_router(crawl_jobs_router)
api_router.include_router(internal_router)
api_router.include_router(import_readiness_router)
api_router.include_router(import_router)
api_router.include_router(review_router)
api_router.include_router(review_actions_router)
api_router.include_router(compare_router)
api_router.include_router(export_router)
