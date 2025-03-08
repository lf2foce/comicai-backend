from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from uuid import uuid4
from typing import List, Optional, Dict, Union
from pydantic import BaseModel, ConfigDict


# Define the expected schema
class DialogueEntry(BaseModel):
    character: str
    text: str

class ComicPage(BaseModel):
    scene: str
    dialogue: List[DialogueEntry]  # List of dialogues
    image_url: str
    image_prompt: str
    text_full: str
    art_style: str
    final_transition: str # Optional[str]=None


class Character(BaseModel):
    name: str
    description: str
    personality: str

class ComicScript(BaseModel):
    title: str
    summary: str
    pages: List[ComicPage]  # A list of pages
    characters: List[Character]
    # characters: Optional[Dict[str, Character]] = None
    
# ✅ Request Model for Generating a Comic
class ComicRequest(SQLModel):
    prompt: str
    user_id: Optional[str] = None  # Clerk User ID (NULL for guests)

# ✅ Response Model for Returning a Comic
class ComicResponse(SQLModel):
    id: Optional[str]
    prompt: Optional[str]
    title: Optional[str]
    summary: Optional[str]
    pages: List[dict]  # Ensure pages are stored as a structured list
    created_at: Optional[str]  # ISO format datetime
    status: str

# ✅ Database Model for Comic
class Comic(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    prompt: str
    title: str
    pages: List[dict] = Field(sa_column=Column(JSONB))  # ✅ Store as JSON in PostgreSQL
    summary: str
    created_at: datetime = Field(default_factory=datetime.now)

    user_id: Optional[str] = Field(default=None)  # Clerk User ID (NULL for guests)
    visibility: str = Field(default="community")  # "community" or "private"
    status: str = Field(default="processing")

    model_config = ConfigDict(arbitrary_types_allowed=True)  # ✅ Allow Pydantic to handle unknown types