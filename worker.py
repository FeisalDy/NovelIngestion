"""
RQ Worker for processing ingestion jobs.

This worker process runs in the background and processes jobs from Redis.

Usage:
    python worker.py
    
    Or with RQ directly:
    rq worker ingestion --url redis://localhost:6379/0

Multiple workers can run simultaneously for parallel processing.
"""
import logging
from redis import Redis
from rq import Worker, Queue, Connection
from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start RQ worker."""
    logger.info("Starting RQ worker for ingestion queue")
    logger.info(f"Redis URL: {settings.redis_url}")
    
    # Connect to Redis
    redis_conn = Redis.from_url(settings.redis_url)
    
    # Create worker with specified queues
    with Connection(redis_conn):
        worker = Worker(
            ['ingestion'],  # Queue names to listen to
            connection=redis_conn,
        )
        
        logger.info("Worker ready. Waiting for jobs...")
        
        # Start processing jobs
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker shutting down...")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
