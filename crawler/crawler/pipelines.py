"""Scrapy pipelines for data processing and storage."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database import SessionLocal
from models import Novel, Chapter, Genre, IngestionJob, IngestionStatus, NovelStatus
from normalizer import ContentCleaner, SlugGenerator, GenreNormalizer
import logging

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """Validate scraped items before processing."""
    
    def process_item(self, item, spider):
        """Validate that required fields are present."""
        required_fields = ['title', 'source_url', 'chapters']
        
        for field in required_fields:
            if not item.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        # Validate we have at least one chapter
        if not item.get('chapters') or len(item['chapters']) == 0:
            raise ValueError("Novel must have at least one chapter")
        
        logger.info(f"Validation passed for: {item['title']}")
        return item


class NormalizationPipeline:
    """Normalize and clean scraped content."""
    
    def __init__(self):
        self.cleaner = ContentCleaner()
    
    def process_item(self, item, spider):
        """Clean and normalize all content."""
        logger.info(f"Normalizing content for: {item['title']}")
        
        # Generate slug
        item['slug'] = SlugGenerator.generate_slug(item['title'])
        
        # Normalize genres
        raw_genres = item.get('genres', [])
        item['normalized_genres'] = GenreNormalizer.normalize_genres(raw_genres)
        
        # Clean chapter content and compute word counts
        total_words = 0
        
        for chapter in item['chapters']:
            # Clean HTML content
            raw_content = chapter.get('content', '')
            clean_content = self.cleaner.clean_html(raw_content)
            chapter['clean_content'] = clean_content
            
            # Count words
            word_count = self.cleaner.count_words(clean_content)
            chapter['word_count'] = word_count
            total_words += word_count
        
        # Store total word count
        item['word_count'] = total_words
        
        logger.info(
            f"Normalized {item['title']}: "
            f"{len(item['chapters'])} chapters, "
            f"{total_words} words"
        )
        
        return item


class DatabasePipeline:
    """Save normalized data to database."""
    
    def __init__(self):
        self.db = None
    
    def open_spider(self, spider):
        """Open database session when spider starts."""
        self.db = SessionLocal()
        logger.info("Database session opened")
    
    def close_spider(self, spider):
        """Close database session when spider closes."""
        if self.db:
            self.db.close()
            logger.info("Database session closed")
    
    def process_item(self, item, spider):
        """Save item to database."""
        try:
            logger.info(f"Saving to database: {item['title']}")
            
            # Update job status to 'saving'
            job_id = item.get('ingestion_job_id')
            if job_id:
                self._update_job_status(job_id, IngestionStatus.SAVING)
            
            # Check if novel already exists
            existing_novel = self.db.query(Novel).filter_by(
                source_url=item['source_url']
            ).first()
            
            if existing_novel:
                logger.info(f"Updating existing novel: {existing_novel.id}")
                novel = self._update_novel(existing_novel, item)
            else:
                logger.info("Creating new novel")
                novel = self._create_novel(item)
            
            # Handle genres
            self._attach_genres(novel, item['normalized_genres'])
            
            # Save chapters
            self._save_chapters(novel, item['chapters'])
            
            # Commit transaction
            self.db.commit()
            
            # Update job status to 'done'
            if job_id:
                self._update_job_status(job_id, IngestionStatus.DONE)
            
            logger.info(f"Successfully saved novel: {novel.id}")
            
            return item
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error: {e}")
            
            # Update job status to 'error'
            job_id = item.get('ingestion_job_id')
            if job_id:
                self._update_job_status(
                    job_id,
                    IngestionStatus.ERROR,
                    error_message=str(e)
                )
            
            raise
    
    def _create_novel(self, item) -> Novel:
        """Create a new novel record."""
        # Map status
        status_map = {
            'ongoing': NovelStatus.ONGOING,
            'completed': NovelStatus.COMPLETED,
        }
        status = status_map.get(
            item.get('status', '').lower(),
            NovelStatus.UNKNOWN
        )
        
        novel = Novel(
            title=item['title'],
            slug=item['slug'],
            synopsis=item.get('synopsis', ''),
            source_url=item['source_url'],
            status=status,
            word_count=item.get('word_count', 0),
        )
        
        self.db.add(novel)
        self.db.flush()  # Get the ID
        
        return novel
    
    def _update_novel(self, novel: Novel, item) -> Novel:
        """Update existing novel record."""
        novel.title = item['title']
        novel.synopsis = item.get('synopsis', '')
        novel.word_count = item.get('word_count', 0)
        
        # Update status if provided
        if item.get('status'):
            status_map = {
                'ongoing': NovelStatus.ONGOING,
                'completed': NovelStatus.COMPLETED,
            }
            status = status_map.get(
                item['status'].lower(),
                NovelStatus.UNKNOWN
            )
            novel.status = status
        
        return novel
    
    def _attach_genres(self, novel: Novel, genre_slugs: list):
        """Attach genres to novel."""
        if not genre_slugs:
            return
        
        # Clear existing genres
        novel.genres.clear()
        
        # Get or create genres
        for slug in genre_slugs:
            genre = self.db.query(Genre).filter_by(slug=slug).first()
            
            if not genre:
                # Create new genre
                # Generate display name from slug
                name = slug.replace('-', ' ').title()
                genre = Genre(name=name, slug=slug)
                self.db.add(genre)
                self.db.flush()
                logger.info(f"Created new genre: {name}")
            
            novel.genres.append(genre)
    
    def _save_chapters(self, novel: Novel, chapters: list):
        """Save chapters for a novel."""
        # Delete existing chapters (fresh import)
        self.db.query(Chapter).filter_by(novel_id=novel.id).delete()
        
        # Create new chapters
        for chapter_data in chapters:
            chapter = Chapter(
                novel_id=novel.id,
                chapter_number=chapter_data['chapter_number'],
                title=chapter_data['chapter_title'],
                content=chapter_data['clean_content'],
                word_count=chapter_data['word_count'],
            )
            self.db.add(chapter)
        
        logger.info(f"Saved {len(chapters)} chapters")
    
    def _update_job_status(
        self,
        job_id: int,
        status: IngestionStatus,
        error_message: str = None
    ):
        """Update ingestion job status."""
        try:
            job = self.db.query(IngestionJob).filter_by(id=job_id).first()
            if job:
                job.status = status
                if error_message:
                    job.error_message = error_message
                self.db.commit()
                logger.info(f"Updated job {job_id} status to {status}")
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
