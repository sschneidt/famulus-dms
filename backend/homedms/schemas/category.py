import uuid
from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_restricted: bool
    is_system_default: bool
    property_mode: str = "none"  # Unterordner pro Objekt-Adresse: none | all | buildings

    model_config = {"from_attributes": True}


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    is_restricted: bool = False
