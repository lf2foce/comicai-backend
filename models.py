from sqlmodel import SQLModel, Field,Column, JSON
from datetime import datetime
from uuid import uuid4
from typing import List
from pydantic import ConfigDict
from pydantic import BaseModel


# Define the expected schema
class DialogueEntry(BaseModel):
    character: str
    text: str

class ComicPage(BaseModel):
    scene: str
    dialogue: List[DialogueEntry]  # List of dialogues
    image_url: str

class ComicScript(BaseModel):
    pages: List[ComicPage]  # A list of pages

# ✅ Request Model for Generating a Comic
class ComicRequest(SQLModel):
    prompt: str

# ✅ Response Model for Returning a Comic
class ComicResponse(SQLModel):
    id: str
    prompt: str
    pages: List[dict]  # Ensure pages are stored as a structured list
    created_at: str  # ISO format datetime

# ✅ Database Model for Comic
class Comic(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    prompt: str
    pages: list = Field(sa_column=Column(JSON))  # ✅ Store as JSON in PostgreSQL
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(arbitrary_types_allowed=True)  # ✅ Allow Pydantic to handle unknown types