"""
CLI utility for managing the novel ingestion backend.

Usage:
    python cli.py ingest <url>              # Ingest a novel
    python cli.py list-jobs                 # List all jobs
    python cli.py list-novels               # List all novels
    python cli.py list-genres               # List all genres
    python cli.py process-queue             # Process queued jobs
"""
import argparse
import sys
from database import SessionLocal
from models import IngestionJob, Novel, Genre, IngestionStatus
from ingestion_queue import SpiderRegistry, CrawlerRunner, IngestionQueue
from config import settings


def cmd_ingest(args):
    """Ingest a novel from URL."""
    url = args.url
    
    # Check if supported
    if not SpiderRegistry.is_supported(url):
        print(f"Error: URL not supported (no spider for this domain)")
        sys.exit(1)
    
    db = SessionLocal()
    try:
        # Check if already exists
        existing = db.query(Novel).filter_by(source_url=url).first()
        if existing:
            print(f"Novel already exists: {existing.title}")
            return
        
        # Create job
        job = IngestionJob(source_url=url, status=IngestionStatus.QUEUED)
        db.add(job)
        db.commit()
        
        print(f"Created job {job.id} for {url}")
        
        # Process immediately if requested
        if args.immediate:
            print("Processing job...")
            crawler_runner = CrawlerRunner(settings.scrapy_project_path)
            queue = IngestionQueue(crawler_runner)
            success = queue.enqueue_job(job.id)
            
            if success:
                print("✓ Job completed successfully")
            else:
                print("✗ Job failed")
        
    finally:
        db.close()


def cmd_list_jobs(args):
    """List all ingestion jobs."""
    db = SessionLocal()
    try:
        jobs = db.query(IngestionJob).order_by(
            IngestionJob.created_at.desc()
        ).limit(args.limit).all()
        
        print(f"\n{'ID':<5} {'Status':<10} {'URL':<50} {'Created':<20}")
        print("-" * 85)
        
        for job in jobs:
            url = job.source_url[:47] + "..." if len(job.source_url) > 50 else job.source_url
            created = job.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{job.id:<5} {job.status.value:<10} {url:<50} {created:<20}")
            
            if job.error_message:
                print(f"      Error: {job.error_message[:80]}")
        
        print(f"\nTotal: {len(jobs)} jobs")
        
    finally:
        db.close()


def cmd_list_novels(args):
    """List all novels."""
    db = SessionLocal()
    try:
        novels = db.query(Novel).order_by(
            Novel.created_at.desc()
        ).limit(args.limit).all()
        
        print(f"\n{'ID':<5} {'Title':<40} {'Status':<12} {'Chapters':<10}")
        print("-" * 67)
        
        for novel in novels:
            title = novel.title[:37] + "..." if len(novel.title) > 40 else novel.title
            chapter_count = len(novel.chapters)
            print(f"{novel.id:<5} {title:<40} {novel.status.value:<12} {chapter_count:<10}")
        
        print(f"\nTotal: {len(novels)} novels")
        
    finally:
        db.close()


def cmd_list_genres(args):
    """List all genres."""
    db = SessionLocal()
    try:
        genres = db.query(Genre).order_by(Genre.name).all()
        
        print(f"\n{'ID':<5} {'Name':<30} {'Slug':<30} {'Novels':<10}")
        print("-" * 75)
        
        for genre in genres:
            novel_count = len(genre.novels)
            print(f"{genre.id:<5} {genre.name:<30} {genre.slug:<30} {novel_count:<10}")
        
        print(f"\nTotal: {len(genres)} genres")
        
    finally:
        db.close()


def cmd_process_queue(args):
    """Process all queued jobs."""
    print("Processing queued jobs...")
    
    crawler_runner = CrawlerRunner(settings.scrapy_project_path)
    queue = IngestionQueue(crawler_runner)
    
    queue.process_queued_jobs()
    
    print("Queue processing complete")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Novel Ingestion Backend CLI"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a novel from URL")
    ingest_parser.add_argument("url", help="Novel URL to ingest")
    ingest_parser.add_argument(
        "--immediate",
        action="store_true",
        help="Process job immediately (don't queue)"
    )
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # List jobs command
    list_jobs_parser = subparsers.add_parser("list-jobs", help="List ingestion jobs")
    list_jobs_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of jobs to show"
    )
    list_jobs_parser.set_defaults(func=cmd_list_jobs)
    
    # List novels command
    list_novels_parser = subparsers.add_parser("list-novels", help="List novels")
    list_novels_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of novels to show"
    )
    list_novels_parser.set_defaults(func=cmd_list_novels)
    
    # List genres command
    list_genres_parser = subparsers.add_parser("list-genres", help="List genres")
    list_genres_parser.set_defaults(func=cmd_list_genres)
    
    # Process queue command
    process_queue_parser = subparsers.add_parser(
        "process-queue",
        help="Process all queued jobs"
    )
    process_queue_parser.set_defaults(func=cmd_process_queue)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Run command
    args.func(args)


if __name__ == "__main__":
    main()
