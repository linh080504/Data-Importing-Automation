from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.schemas.template import CleanTemplateListItem, CleanTemplateListResponse, CleanTemplateResponse, DeleteTemplateResponse
from app.services.template_parser import TemplateParseError, parse_template_csv

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=CleanTemplateListResponse)
def list_templates(db: Session = Depends(get_db)) -> CleanTemplateListResponse:
    templates = db.query(CleanTemplate).order_by(CleanTemplate.created_at.desc()).all()
    return CleanTemplateListResponse(
        templates=[
            CleanTemplateListItem(
                id=str(template.id),
                template_name=template.template_name,
                file_name=template.file_name,
                column_count=template.column_count,
            )
            for template in templates
        ]
    )


@router.post("/upload", response_model=CleanTemplateResponse, status_code=status.HTTP_201_CREATED)
def upload_template(
    template_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> CleanTemplateResponse:
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV template files are supported")

    content = file.file.read()
    try:
        parsed = parse_template_csv(content)
    except TemplateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.query(CleanTemplate).filter(CleanTemplate.template_name == template_name).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Template name already exists")

    template = CleanTemplate(
        template_name=template_name,
        file_name=file.filename or f"{template_name}.csv",
        column_count=len(parsed.columns),
        columns=parsed.columns,
        sample_row=parsed.sample_row,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return CleanTemplateResponse(
        id=str(template.id),
        template_name=template.template_name,
        file_name=template.file_name,
        column_count=template.column_count,
        columns=template.columns,
        sample_row=template.sample_row,
    )


@router.delete("/{template_id}", response_model=DeleteTemplateResponse)
def delete_template(template_id: str, db: Session = Depends(get_db)) -> DeleteTemplateResponse:
    template = db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    linked_job = db.query(CrawlJob).filter(CrawlJob.clean_template_id == template_id).one_or_none()
    if linked_job is not None:
        raise HTTPException(status_code=409, detail="Template is currently used by an existing crawl job")

    db.delete(template)
    db.commit()

    return DeleteTemplateResponse(id=str(template.id), message="Template deleted")
