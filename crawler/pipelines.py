"""Scrapy pipelines for data processing and storage."""
import os
import sys

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
        logger.info(f"=== VALIDATION PIPELINE START ===")
        logger.info(f"Item keys: {list(item.keys())}")
        logger.info(f"Title: {item.get('title', 'N/A')}")
        logger.info(f"Source URL: {item.get('source_url', 'N/A')}")
        logger.info(f"Is one-shot: {item.get('is_one_shot', False)}")
        logger.info(f"Number of chapters: {len(item.get('chapters', []))}")
        
        required_fields = ['title', 'source_url']

        for field in required_fields:
            if not item.get(field):
                raise ValueError(f"Missing required field: {field}")

        # Check if it's a one-shot or a series
        is_one_shot = item.get('is_one_shot', False)
        chapters = item.get('chapters', [])

        # TODO handle on shot differently
        if is_one_shot:
            # One-shot must have exactly one chapter or content directly
            if not chapters or len(chapters) != 1:
                if not item.get('content'):
                    raise ValueError("One-shot novel must have content or exactly one chapter")
        else:
            # Series must have at least one chapter
            if not chapters or len(chapters) == 0:
                raise ValueError("Novel series must have at least one chapter")

        logger.info(f"Validation passed for: {item['title']} (one_shot={is_one_shot})")
        logger.info(f"=== VALIDATION PIPELINE END - PASSED ===")
        return item


class NormalizationPipeline:
    """Normalize and clean scraped content."""

    def __init__(self):
        self.cleaner = ContentCleaner()

    def process_item(self, item, spider):
        """Clean and normalize all content."""
        logger.info(f"=== NORMALIZATION PIPELINE START ===")
        logger.info(f"Normalizing content for: {item['title']}")

        # Generate slug
        item['slug'] = SlugGenerator.generate_slug(item['title'])

        # Normalize genres
        raw_genres = item.get('genres', [])
        item['normalized_genres'] = GenreNormalizer.normalize_genres(raw_genres)

        # Check if one-shot
        is_one_shot = item.get('is_one_shot', False)

        # Clean chapter content and compute word counts
        total_words = 0
        chapters = item.get('chapters', [])

        # TODO handle on shot differently
        # Handle one-shot with direct content
        if is_one_shot and not chapters and item.get('content'):
            # Convert direct content to chapter format
            raw_content = item['content']
            clean_content = self.cleaner.clean_html(raw_content)
            word_count = self.cleaner.count_words(clean_content)
            chapters = [{
                'chapter_number': 1,
                'chapter_title': item['title'],
                'content': raw_content,
                'clean_content': clean_content,
                'word_count': word_count
            }]
            item['chapters'] = chapters
            total_words = word_count
        else:
            # Normal chapter processing
            for chapter in chapters:
                # Clean HTML content
                raw_content = chapter.get('content', '')
                clean_content = self.cleaner.clean_html(raw_content)
                chapter['clean_content'] = clean_content

                # Count words
                word_count = self.cleaner.count_words(clean_content)
                chapter['word_count'] = word_count
                total_words += word_count
                
                # Normalize chapter genres if present
                chapter_genres = chapter.get('genres', [])
                if chapter_genres:
                    chapter['normalized_genres'] = GenreNormalizer.normalize_genres(chapter_genres)
                else:
                    chapter['normalized_genres'] = []

        # Store total word count
        item['word_count'] = total_words

        logger.info(
            f"Normalized {item['title']}: "
            f"{len(chapters)} chapters, "
            f"{total_words} words (one_shot={is_one_shot})"
        )
        logger.info(f"=== NORMALIZATION PIPELINE END - SUCCESS ===")

        return item


class DatabasePipeline:
    """Save normalized data to database."""

    def __init__(self):
        self.db = None

    def open_spider(self, spider):
        """Open database session when spider starts."""
        try:
            self.db = SessionLocal()
            logger.info("Database session opened")
        except Exception as e:
            logger.error(f"Failed to open database session: {e}")
            raise

    def close_spider(self, spider):
        """Close database session when spider closes."""
        if self.db:
            try:
                self.db.close()
                logger.info("Database session closed")
            except Exception as e:
                logger.error(f"Error closing database session: {e}")

    def process_item(self, item, spider):
        """Save item to database."""
        logger.info(f"=== DATABASE PIPELINE START ===")
        logger.info(f"Attempting to save: {item.get('title', 'N/A')}")
        logger.info(f"Job ID: {item.get('ingestion_job_id', 'N/A')}")
        logger.info(f"Database session active: {self.db is not None}")
        
        try:
            is_one_shot = item.get('is_one_shot', False)

            # TODO handle on shot differently
            if is_one_shot:
                logger.info(f"Processing as ONE-SHOT chapter: {item['title']}")
                self._save_one_shot_chapter(item)
            else:
                logger.info(f"Processing as NOVEL SERIES: {item['title']}")

                # Update job status to 'saving'
                job_id = item.get('ingestion_job_id')
                logger.info(f"Job ID for status update: {job_id}")
                if job_id:
                    logger.info(f"Updating job {job_id} status to SAVING")
                    self._update_job_status(job_id, IngestionStatus.SAVING)
                else:
                    logger.warning("No job_id provided in item")

                # Check if novel already exists
                logger.info(f"Checking if novel exists: {item['source_url']}")
                existing_novel = self.db.query(Novel).filter_by(
                    source_url=item['source_url']
                ).first()

                if existing_novel:
                    logger.info(f"FOUND existing novel with ID: {existing_novel.id}")
                    novel = self._update_novel(existing_novel, item)
                    logger.info(f"Novel updated successfully")
                else:
                    logger.info("Novel NOT found - creating new novel")
                    novel = self._create_novel(item)
                    logger.info(f"New novel created with ID: {novel.id}")

                # Handle genres
                logger.info(f"Attaching {len(item['normalized_genres'])} genres to novel")
                self._attach_genres(novel, item['normalized_genres'])
                logger.info(f"Genres attached successfully")

                # Save chapters
                logger.info(f"Saving {len(item['chapters'])} chapters")
                self._save_chapters(novel, item['chapters'])
                logger.info(f"All chapters saved successfully")

                # Commit transaction
                logger.info("Committing database transaction...")
                self.db.commit()
                logger.info("Database transaction committed successfully")

                # Update job status to 'done'
                if job_id:
                    logger.info(f"Updating job {job_id} status to DONE")
                    self._update_job_status(job_id, IngestionStatus.DONE)
                    logger.info(f"Job {job_id} marked as DONE")

                logger.info(f"✓ Successfully saved novel: {novel.id}")
                logger.info(f"=== DATABASE PIPELINE END - SUCCESS ===")

            return item

        except Exception as e:
            logger.error(f"=== DATABASE PIPELINE ERROR ===")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {e}")
            import traceback
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            logger.error(f"Item being processed: {item.get('title', 'N/A')}")
            
            logger.info("Rolling back database transaction...")
            self.db.rollback()
            logger.info("Rollback completed")

            # Update job status to 'error'
            job_id = item.get('ingestion_job_id')
            logger.info(f"Attempting to update job status to ERROR for job_id: {job_id}")
            if job_id:
                try:
                    self._update_job_status(
                        job_id,
                        IngestionStatus.ERROR,
                        error_message=str(e)
                    )
                    logger.info(f"Successfully updated job {job_id} to ERROR status")
                except Exception as update_error:
                    logger.error(f"Failed to update job status: {update_error}")
            else:
                logger.warning("No job_id available to update status")

            logger.error(f"=== DATABASE PIPELINE END - FAILED ===")
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

    def _attach_genres_to_chapter(self, chapter: Chapter, genre_slugs: list):
        """Attach genres to a chapter (for one-shots)."""
        if not genre_slugs:
            return

        # Clear existing genres
        chapter.genres.clear()

        # Get or create genres
        for slug in genre_slugs:
            genre = self.db.query(Genre).filter_by(slug=slug).first()

            if not genre:
                # Create new genre
                name = slug.replace('-', ' ').title()
                genre = Genre(name=name, slug=slug)
                self.db.add(genre)
                self.db.flush()
                logger.info(f"Created new genre: {name}")

            chapter.genres.append(genre)

    def _save_chapters(self, novel: Novel, chapters: list):
        """Save chapters for a novel series."""
        # Delete existing chapters (fresh import)
        self.db.query(Chapter).filter_by(novel_id=novel.id).delete()

        # Create new chapters
        for chapter_data in chapters:
            chapter = Chapter(
                novel_id=novel.id,
                chapter_number=chapter_data['chapter_number'],
                title=chapter_data['chapter_title'],
                slug=None,  # Series chapters don't need slugs
                content=chapter_data['clean_content'],
                source_url=chapter_data.get('source_url'),
                word_count=chapter_data['word_count'],
                is_one_shot=False,  # Series chapters are not one-shots
            )
            self.db.add(chapter)
            self.db.flush()  # Get the chapter ID
            
            # Attach genres to chapter if present
            chapter_genres = chapter_data.get('normalized_genres', [])
            if chapter_genres:
                self._attach_genres_to_chapter(chapter, chapter_genres)
                logger.info(f"Attached {len(chapter_genres)} genres to chapter {chapter.chapter_number}")

        logger.info(f"Saved {len(chapters)} chapters for novel series")

    def _save_one_shot_chapter(self, item):
        """Save a standalone one-shot chapter (no parent novel)."""
        try:
            # Update job status to 'saving'
            job_id = item.get('ingestion_job_id')
            if job_id:
                self._update_job_status(job_id, IngestionStatus.SAVING)

            # Check if one-shot already exists by source URL
            chapter_data = item['chapters'][0]  # One-shot has exactly one chapter

            # Generate unique slug for the one-shot
            chapter_slug = SlugGenerator.generate_slug(item['title'])

            # Check if already exists
            existing_chapter = self.db.query(Chapter).filter_by(
                slug=chapter_slug,
                is_one_shot=True
            ).first()

            if existing_chapter:
                logger.info(f"Updating existing one-shot: {existing_chapter.id}")
                existing_chapter.title = item['title']
                existing_chapter.content = chapter_data['clean_content']
                existing_chapter.word_count = chapter_data['word_count']
                existing_chapter.source_url = item.get('source_url')
                chapter = existing_chapter
            else:
                logger.info(f"Creating new one-shot chapter: {item['title']}")
                chapter = Chapter(
                    novel_id=None,  # No parent novel
                    chapter_number=1,  # Always 1 for one-shots
                    title=item['title'],
                    slug=chapter_slug,
                    content=chapter_data['clean_content'],
                    source_url=item.get('source_url'),
                    word_count=chapter_data['word_count'],
                    is_one_shot=True,
                )
                self.db.add(chapter)
                self.db.flush()  # Get the ID

            # Handle genres for one-shot
            self._attach_genres_to_chapter(chapter, item.get('normalized_genres', []))

            # Commit transaction
            self.db.commit()

            # Update job status to 'done'
            if job_id:
                self._update_job_status(job_id, IngestionStatus.DONE)

            logger.info(f"Successfully saved one-shot chapter: {item['title']}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving one-shot: {e}")

            # Update job status to 'error'
            job_id = item.get('ingestion_job_id')
            if job_id:
                self._update_job_status(
                    job_id,
                    IngestionStatus.ERROR,
                    error_message=str(e)
                )
            raise

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
