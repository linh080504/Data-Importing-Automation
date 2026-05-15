from pydantic import BaseModel, ConfigDict


class TemplateColumn(BaseModel):
    name: str
    order: int


class CleanTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_name: str
    file_name: str
    column_count: int
    columns: list[TemplateColumn]
    sample_row: dict | None


class CleanTemplateListItem(BaseModel):
    id: str
    template_name: str
    file_name: str
    column_count: int


class CleanTemplateListResponse(BaseModel):
    templates: list[CleanTemplateListItem]


class DeleteTemplateResponse(BaseModel):
    id: str
    message: str
