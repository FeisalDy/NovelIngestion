"""Ingestion job queue and crawler management."""
import subprocess
import logging
from typing import Optional
from urllib.parse import urlparse
from database import SessionLocal
from models import IngestionJob, IngestionStatus

logger = logging.getLogger(__name__)


class SpiderRegistry:
    """
    Registry mapping domains to spider names.
    
    Used to select the appropriate spider for a given URL.
    """
    
    DOMAIN_SPIDER_MAP = {
        'royalroad.com': 'royalroad',
        'www.royalroad.com': 'royalroad',
        'example.com': 'example_site',
        'www.example.com': 'example_site',
        # Add more domain -> spider mappings here
    }
    
    @classmethod
    def get_spider_for_url(cls, url: str) -> Optional[str]:
        """
        Determine which spider to use for a given URL.
        
        Args:
            url: The source URL
            
        Returns:
            Spider name or None if no spider found
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        spider_name = cls.DOMAIN_SPIDER_MAP.get(domain)
        
        if not spider_name:
            logger.warning(f"No spider registered for domain: {domain}")
        
        return spider_name
    
    @classmethod
    def is_supported(cls, url: str) -> bool:
        """Check if URL is supported."""
        return cls.get_spider_for_url(url) is not None


class CrawlerRunner:
    """
    Run Scrapy spiders programmatically.
    
    Handles spider execution for ingestion jobs.
    """
    
    def __init__(self, scrapy_project_path: str = "./crawler"):
        self.scrapy_project_path = scrapy_project_path
    
    def run_spider(self, spider_name: str, url: str, job_id: int) -> bool:
        """
        Run a spider for a specific URL and job.
        
        Args:
            spider_name: Name of the spider to run
            url: URL to crawl
            job_id: Ingestion job ID
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Running spider '{spider_name}' for job {job_id}")
        
        try:
            # Update job status to 'crawling'
            self._update_job_status(job_id, IngestionStatus.CRAWLING)
            
            # Build scrapy command
            command = [
                'scrapy', 'crawl', spider_name,
                '-a', f'url={url}',
                '-a', f'job_id={job_id}',
            ]
            
            # Run scrapy in subprocess
            result = subprocess.run(
                command,
                cwd=self.scrapy_project_path,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Spider completed successfully for job {job_id}")
                return True
            else:
                logger.error(f"Spider failed for job {job_id}")
                logger.error(f"stdout: {result.stdout}")
                logger.error(f"stderr: {result.stderr}")
                
                self._update_job_status(
                    job_id,
                    IngestionStatus.ERROR,
                    error_message=result.stderr[:1000]
                )
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Spider timeout for job {job_id}")
            self._update_job_status(
                job_id,
                IngestionStatus.ERROR,
                error_message="Spider execution timed out"
            )
            return False
            
        except Exception as e:
            logger.error(f"Spider execution error for job {job_id}: {e}")
            self._update_job_status(
                job_id,
                IngestionStatus.ERROR,
                error_message=str(e)
            )
            return False
    
    def _update_job_status(
        self,
        job_id: int,
        status: IngestionStatus,
        error_message: str = None
    ):
        """Update job status in database."""
        db = SessionLocal()
        try:
            job = db.query(IngestionJob).filter_by(id=job_id).first()
            if job:
                job.status = status
                if error_message:
                    job.error_message = error_message
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            db.rollback()
        finally:
            db.close()


class IngestionQueue:
    """
    Simple ingestion queue manager.
    
    For production, replace with Redis-based queue (RQ, Celery, etc.)
    """
    
    def __init__(self, crawler_runner: CrawlerRunner):
        self.crawler_runner = crawler_runner
    
    def enqueue_job(self, job_id: int) -> bool:
        """
        Enqueue an ingestion job.
        
        Args:
            job_id: ID of the ingestion job
            
        Returns:
            True if enqueued successfully
        """
        db = SessionLocal()
        try:
            job = db.query(IngestionJob).filter_by(id=job_id).first()
            
            if not job:
                logger.error(f"Job {job_id} not found")
                return False
            
            # Get spider for URL
            spider_name = SpiderRegistry.get_spider_for_url(job.source_url)
            
            if not spider_name:
                job.status = IngestionStatus.ERROR
                job.error_message = "No spider available for this URL"
                db.commit()
                return False
            
            # For now, run synchronously
            # In production, use background task queue
            logger.info(f"Processing job {job_id} synchronously")
            
            success = self.crawler_runner.run_spider(
                spider_name,
                job.source_url,
                job_id
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to enqueue job {job_id}: {e}")
            return False
        finally:
            db.close()
    
    def process_queued_jobs(self):
        """
        Process all queued jobs.
        
        This can be called by a background worker.
        """
        db = SessionLocal()
        try:
            queued_jobs = db.query(IngestionJob).filter_by(
                status=IngestionStatus.QUEUED
            ).all()
            
            logger.info(f"Found {len(queued_jobs)} queued jobs")
            
            for job in queued_jobs:
                logger.info(f"Processing job {job.id}")
                self.enqueue_job(job.id)
                
        except Exception as e:
            logger.error(f"Error processing queued jobs: {e}")
        finally:
            db.close()
