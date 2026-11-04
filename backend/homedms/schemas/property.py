"""Schemas fuer /properties - Objekte (Haus/Wohnung) fuer die Ablage pro Adresse."""
import uuid

from pydantic import BaseModel, Field


class PropertyResponse(BaseModel):
    id: uuid.UUID
    name: str
    street: str
    postal_code: str
    city: str
    document_count: int = 0

    model_config = {"from_attributes": True}


class PropertyCreate(BaseModel):
    """Objekt von Hand anlegen. Die Adresse ist freiwillig; wenn angegeben, dann komplett."""

    name: str = Field(min_length=1, max_length=200)
    street: str = Field(default="", max_length=200)
    postal_code: str = Field(default="", max_length=10)
    city: str = Field(default="", max_length=100)


class PropertyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PropertyMerge(BaseModel):
    """Dieses Objekt in ein anderes ueberfuehren (z. B. doppelt erkannte Adresse)."""

    into_id: uuid.UUID
