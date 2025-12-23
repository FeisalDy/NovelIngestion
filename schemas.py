"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, HttpUrl, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from models import IngestionStatus, NovelStatus


# Ingestion Schemas
class IngestionRequest(BaseModel):
    """Request to ingest a novel from URL."""
    url: HttpUrl = Field(..., description="URL of the novel to ingest")


class IngestionResponse(BaseModel):
    """Response after creating ingestion job."""
    job_id: int
    status: IngestionStatus
    message: str
    
    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Job status response."""
    id: int
    source_url: str
    status: IngestionStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Novel Schemas
class GenreSchema(BaseModel):
    """Genre schema for API responses."""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class NovelListItem(BaseModel):
    """Novel list item for paginated responses."""
    id: int
    title: str
    slug: str
    synopsis: Optional[str] = None
    status: NovelStatus
    word_count: int
    created_at: datetime
    genres: List[GenreSchema] = []
    
    model_config = ConfigDict(from_attributes=True)


class NovelDetail(BaseModel):
    """Detailed novel information."""
    id: int
    title: str
    slug: str
    synopsis: Optional[str] = None
    status: NovelStatus
    word_count: int
    created_at: datetime
    updated_at: datetime
    genres: List[GenreSchema] = []
    chapter_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


class ChapterListItem(BaseModel):
    """Chapter list item."""
    id: int
    chapter_number: int
    title: str
    word_count: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ChapterDetail(BaseModel):
    """Detailed chapter information with content."""
    id: int
    novel_id: int
    chapter_number: int
    title: str
    content: str
    word_count: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[BaseModel]
    total: int
    page: int
    page_size: int
    total_pages: int


class NovelListResponse(BaseModel):
    """Paginated novel list response."""
    items: List[NovelListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChapterListResponse(BaseModel):
    """Paginated chapter list response."""
    items: List[ChapterListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class GenreListResponse(BaseModel):
    """Genre list response."""
    items: List[GenreSchema]
    total: int


class GenreDetailResponse(BaseModel):
    """Genre detail with novel list."""
    genre: GenreSchema
    novels: NovelListResponse
