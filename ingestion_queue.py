"""Ingestion job queue and crawler management."""
import logging
import subprocess
from typing import Optional
from urllib.parse import urlparse

from redis import Redis
from rq import Queue

from config import settings
from database import SessionLocal
from models import IngestionJob, IngestionStatus

logger = logging.getLogger(__name__)

# Redis connection
redis_conn = Redis.from_url(settings.redis_url)
# RQ Queue
job_queue = Queue('ingestion', connection=redis_conn)


class SpiderRegistry:
    """
    Registry mapping domains to spider names.
    
    Used to select the appropriate spider for a given URL.
    """

    DOMAIN_SPIDER_MAP = {
        'www.pixiv.net': 'pixiv',
        'pixiv.net': 'pixiv',
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

    def __init__(self, scrapy_project_path: str = None):
        # scrapy_project_path is deprecated, kept for backward compatibility
        # Always run from project root
        self.scrapy_project_path = None

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
        logger.info(f"=== Starting spider '{spider_name}' for job {job_id} ===")
        logger.info(f"Target URL: {url}")

        try:
            # Update job status to 'crawling'
            logger.info(f"Updating job {job_id} status to CRAWLING")
            self._update_job_status(job_id, IngestionStatus.CRAWLING)

            # Build scrapy command
            command = [
                'scrapy', 'crawl', spider_name,
                '-a', f'url={url}',
                '-a', f'job_id={job_id}',
            ]

            logger.info(f"Executing command: {' '.join(command)}")
            logger.info("Starting scrapy subprocess...")
            
            # Run scrapy in subprocess from project root (not from crawler subdir)
            # This ensures that the imports in pipelines.py work correctly
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            logger.info(f"Scrapy process completed with return code: {result.returncode}")
            
            # Log stdout if present
            if result.stdout:
                logger.info(f"=== Scrapy Output (stdout) ===")
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        logger.info(f"  {line}")
            
            # Log stderr if present
            if result.stderr:
                logger.warning(f"=== Scrapy Warnings/Errors (stderr) ===")
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        logger.warning(f"  {line}")

            if result.returncode == 0:
                # Check if there were spider errors/exceptions in stderr
                has_errors = any([
                    'spider_exceptions' in result.stderr.lower(),
                    'error' in result.stderr.lower() and 'spider error' in result.stderr.lower(),
                    'no valid novel data collected' in result.stderr.lower(),
                    'log_count/error' in result.stderr.lower()
                ])
                
                if has_errors:
                    logger.error(f"=== Spider completed with ERRORS for job {job_id} ===")
                    logger.error("Detected errors in spider output despite return code 0")
                    
                    # Extract error message from stderr
                    error_lines = [line for line in result.stderr.split('\n') if 'ERROR' in line]
                    error_message = '\n'.join(error_lines[:5]) if error_lines else result.stderr[:1000]
                    
                    self._update_job_status(
                        job_id,
                        IngestionStatus.ERROR,
                        error_message=error_message
                    )
                    return False
                else:
                    # self._update_job_status(job_id, IngestionStatus.DONE)
                    logger.info(f"=== Spider completed successfully for job {job_id} ===")
                    return True
            else:
                logger.error(f"=== Spider failed for job {job_id} with return code {result.returncode} ===")
                logger.error(f"Full stdout: {result.stdout[:2000]}")
                logger.error(f"Full stderr: {result.stderr[:2000]}")

                self._update_job_status(
                    job_id,
                    IngestionStatus.ERROR,
                    error_message=result.stderr[:1000]
                )
                return False

        except subprocess.TimeoutExpired as e:
            logger.error(f"=== Spider TIMEOUT for job {job_id} ===")
            logger.error(f"Timeout occurred after 3600 seconds")
            if hasattr(e, 'stdout') and e.stdout:
                logger.error(f"Partial stdout: {e.stdout[:1000]}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"Partial stderr: {e.stderr[:1000]}")
            self._update_job_status(
                job_id,
                IngestionStatus.ERROR,
                error_message="Spider execution timed out after 1 hour"
            )
            return False

        except Exception as e:
            logger.error(f"=== Spider EXCEPTION for job {job_id} ===")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {e}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            self._update_job_status(
                job_id,
                IngestionStatus.ERROR,
                error_message=str(e)[:1000]
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
    Redis-based ingestion queue manager using RQ.
    
    Enqueues jobs to Redis for background worker processing.
    """

    def __init__(self, queue: Queue = None):
        """
        Initialize queue.
        
        Args:
            queue: RQ Queue instance (uses default if None)
        """
        self.queue = queue or job_queue

    def enqueue_job(self, job_id: int) -> bool:
        """
        Enqueue an ingestion job to Redis.
        
        Non-blocking - returns immediately after queueing.
        
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

            # Enqueue to Redis (non-blocking)
            logger.info(f"Enqueueing job {job_id} to Redis")

            self.queue.enqueue(
                'ingestion_queue.process_job',  # Function to call
                job_id,  # Arguments
                job_timeout='1h',  # Max execution time
                result_ttl=86400,  # Keep result for 24 hours
                failure_ttl=604800,  # Keep failures for 7 days
            )

            logger.info(f"Job {job_id} enqueued successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to enqueue job {job_id}: {e}")
            return False
        finally:
            db.close()

    def process_queued_jobs(self):
        """
        Process all queued DB jobs by enqueueing them to Redis.
        
        Useful for initial migration or recovery.
        """
        db = SessionLocal()
        try:
            queued_jobs = db.query(IngestionJob).filter_by(
                status=IngestionStatus.QUEUED
            ).all()

            logger.info(f"Found {len(queued_jobs)} queued jobs")

            for job in queued_jobs:
                logger.info(f"Enqueueing job {job.id}")
                self.enqueue_job(job.id)

        except Exception as e:
            logger.error(f"Error processing queued jobs: {e}")
        finally:
            db.close()


# Worker function (called by RQ worker)
def process_job(job_id: int):
    """
    Process a single ingestion job.
    
    This function is called by RQ workers.
    
    Args:
        job_id: ID of the ingestion job to process
    """
    logger.info(f"="*60)
    logger.info(f"WORKER: Starting to process job {job_id}")
    logger.info(f"="*60)

    db = SessionLocal()
    try:
        job = db.query(IngestionJob).filter_by(id=job_id).first()

        if not job:
            logger.error(f"WORKER: Job {job_id} not found in database")
            return False
        
        logger.info(f"WORKER: Job {job_id} details:")
        logger.info(f"  - URL: {job.source_url}")
        logger.info(f"  - Current status: {job.status}")
        logger.info(f"  - Retry count: {job.retry_count}")

        # Get spider name
        spider_name = SpiderRegistry.get_spider_for_url(job.source_url)

        if not spider_name:
            logger.error(f"WORKER: No spider registered for URL: {job.source_url}")
            return False
        
        logger.info(f"WORKER: Selected spider '{spider_name}' for this job")

        # Create crawler runner and execute
        crawler_runner = CrawlerRunner(settings.scrapy_project_path)
        logger.info(f"WORKER: Starting crawler execution...")
        
        success = crawler_runner.run_spider(
            spider_name,
            job.source_url,
            job_id
        )

        logger.info(f"="*60)
        logger.info(f"WORKER: Job {job_id} processing completed: {'SUCCESS' if success else 'FAILED'}")
        logger.info(f"="*60)
        return success

    except Exception as e:
        logger.error(f"="*60)
        logger.error(f"WORKER: FATAL ERROR processing job {job_id}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {e}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error(f"="*60)

        # Update job status to ERROR
        try:
            job = db.query(IngestionJob).filter_by(id=job_id).first()
            if job:
                logger.info(f"WORKER: Updating job {job_id} status to ERROR")
                job.status = IngestionStatus.ERROR
                job.error_message = str(e)[:1000]
                db.commit()
                logger.info(f"WORKER: Job status updated successfully")
        except Exception as update_error:
            logger.error(f"WORKER: Failed to update job status: {update_error}")

        return False

    finally:
        db.close()
        logger.info(f"WORKER: Database connection closed for job {job_id}")
