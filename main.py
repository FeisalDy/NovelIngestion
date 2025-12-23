"""FastAPI application - main entry point."""
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional
import logging

from database import get_db
from models import Novel, Chapter, Genre, IngestionJob, IngestionStatus
from schemas import (
    IngestionRequest, IngestionResponse, JobStatusResponse,
    NovelListResponse, NovelDetail, NovelListItem,
    ChapterListResponse, ChapterDetail, ChapterListItem,
    GenreListResponse, GenreSchema, GenreDetailResponse
)
from ingestion_queue import SpiderRegistry, CrawlerRunner, IngestionQueue
from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Novel Ingestion API",
    description="Backend API for novel crawling, ingestion, and reading",
    version="1.0.0",
)

# Initialize queue (no crawler needed - handled by worker)
ingestion_queue = IngestionQueue()


# ============================================================================
# Ingestion Endpoints
# ============================================================================

@app.post("/ingest", response_model=IngestionResponse, tags=["Ingestion"])
async def ingest_novel(
    request: IngestionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a novel from URL.
    
    Creates an ingestion job and enqueues it for crawling.
    Returns immediately without waiting for crawl to complete.
    """
    url = str(request.url)
    
    # Validate URL is supported
    if not SpiderRegistry.is_supported(url):
        raise HTTPException(
            status_code=400,
            detail="URL domain not supported. No spider available for this site."
        )
    
    # Check if URL already exists
    result = await db.execute(
        select(Novel).where(Novel.source_url == url)
    )
    existing_novel = result.scalar_one_or_none()
    
    if existing_novel:
        return IngestionResponse(
            job_id=0,
            status=IngestionStatus.DONE,
            message=f"Novel already exists: {existing_novel.title}"
        )
    
    # Create ingestion job
    job = IngestionJob(
        source_url=url,
        status=IngestionStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(f"Created ingestion job {job.id} for {url}")
    
    # Enqueue job in background
    background_tasks.add_task(ingestion_queue.enqueue_job, job.id)
    
    return IngestionResponse(
        job_id=job.id,
        status=job.status,
        message="Ingestion job created and queued"
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["Ingestion"])
async def get_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get status of an ingestion job."""
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse.model_validate(job)


# ============================================================================
# Novel Endpoints (Read-Only)
# ============================================================================

@app.get("/novels", response_model=NovelListResponse, tags=["Novels"])
async def list_novels(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    genre: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all novels with pagination.
    
    Optionally filter by search term or genre.
    """
    # Base query
    query = select(Novel).options(selectinload(Novel.genres))
    
    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Novel.title.ilike(search_term),
                Novel.synopsis.ilike(search_term)
            )
        )
    
    if genre:
        # Filter by genre slug
        query = query.join(Novel.genres).where(Genre.slug == genre)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    novels = result.scalars().all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return NovelListResponse(
        items=[NovelListItem.model_validate(n) for n in novels],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/novels/{slug}", response_model=NovelDetail, tags=["Novels"])
async def get_novel(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a specific novel."""
    result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.genres))
        .where(Novel.slug == slug)
    )
    novel = result.scalar_one_or_none()
    
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    # Get chapter count
    chapter_count_result = await db.execute(
        select(func.count(Chapter.id)).where(Chapter.novel_id == novel.id)
    )
    chapter_count = chapter_count_result.scalar()
    
    # Convert to response model
    novel_dict = {
        "id": novel.id,
        "title": novel.title,
        "slug": novel.slug,
        "synopsis": novel.synopsis,
        "status": novel.status,
        "word_count": novel.word_count,
        "created_at": novel.created_at,
        "updated_at": novel.updated_at,
        "genres": [GenreSchema.model_validate(g) for g in novel.genres],
        "chapter_count": chapter_count,
    }
    
    return NovelDetail(**novel_dict)


@app.get("/novels/{slug}/chapters", response_model=ChapterListResponse, tags=["Chapters"])
async def list_chapters(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List all chapters for a novel."""
    # Get novel
    novel_result = await db.execute(
        select(Novel).where(Novel.slug == slug)
    )
    novel = novel_result.scalar_one_or_none()
    
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    # Get total chapter count
    count_result = await db.execute(
        select(func.count(Chapter.id)).where(Chapter.novel_id == novel.id)
    )
    total = count_result.scalar()
    
    # Get chapters
    offset = (page - 1) * page_size
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_number)
        .offset(offset)
        .limit(page_size)
    )
    chapters = chapters_result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return ChapterListResponse(
        items=[ChapterListItem.model_validate(c) for c in chapters],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/novels/{slug}/chapters/{chapter_number}", response_model=ChapterDetail, tags=["Chapters"])
async def get_chapter(
    slug: str,
    chapter_number: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific chapter's content."""
    # Get novel
    novel_result = await db.execute(
        select(Novel).where(Novel.slug == slug)
    )
    novel = novel_result.scalar_one_or_none()
    
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    # Get chapter
    chapter_result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == novel.id,
            Chapter.chapter_number == chapter_number
        )
    )
    chapter = chapter_result.scalar_one_or_none()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    return ChapterDetail.model_validate(chapter)


# ============================================================================
# Genre Endpoints
# ============================================================================

@app.get("/genres", response_model=GenreListResponse, tags=["Genres"])
async def list_genres(db: AsyncSession = Depends(get_db)):
    """List all genres."""
    result = await db.execute(
        select(Genre).order_by(Genre.name)
    )
    genres = result.scalars().all()
    
    return GenreListResponse(
        items=[GenreSchema.model_validate(g) for g in genres],
        total=len(genres)
    )


@app.get("/genres/{slug}", response_model=GenreDetailResponse, tags=["Genres"])
async def get_genre(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get genre details with associated novels."""
    # Get genre
    genre_result = await db.execute(
        select(Genre).where(Genre.slug == slug)
    )
    genre = genre_result.scalar_one_or_none()
    
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    
    # Get novels for this genre
    count_result = await db.execute(
        select(func.count(Novel.id))
        .join(Novel.genres)
        .where(Genre.id == genre.id)
    )
    total = count_result.scalar()
    
    offset = (page - 1) * page_size
    novels_result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.genres))
        .join(Novel.genres)
        .where(Genre.id == genre.id)
        .offset(offset)
        .limit(page_size)
    )
    novels = novels_result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    novels_response = NovelListResponse(
        items=[NovelListItem.model_validate(n) for n in novels],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )
    
    return GenreDetailResponse(
        genre=GenreSchema.model_validate(genre),
        novels=novels_response
    )


@app.get("/genres/{slug}/novels", response_model=NovelListResponse, tags=["Genres"])
async def list_novels_by_genre(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List novels for a specific genre."""
    # Verify genre exists
    genre_result = await db.execute(
        select(Genre).where(Genre.slug == slug)
    )
    genre = genre_result.scalar_one_or_none()
    
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    
    # Get novels
    return await list_novels(
        page=page,
        page_size=page_size,
        genre=slug,
        db=db
    )


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "novel-ingestion"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )
