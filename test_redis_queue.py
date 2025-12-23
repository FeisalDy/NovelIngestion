"""
Test script for Redis queue functionality.

Run this after starting Redis and worker to verify the system works.

Usage:
    python test_redis_queue.py
"""
import sys
import time
from redis import Redis
from rq import Queue
from database import SessionLocal
from models import IngestionJob, IngestionStatus
from ingestion_queue import SpiderRegistry, IngestionQueue
from config import settings


def print_section(title):
    """Print section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_redis_connection():
    """Test Redis connection."""
    print_section("1. Testing Redis Connection")
    
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        response = redis_conn.ping()
        
        if response:
            print("✓ Redis connection successful")
            print(f"  URL: {settings.redis_url}")
            return True
        else:
            print("✗ Redis ping failed")
            return False
            
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        print("\nMake sure Redis is running:")
        print("  redis-server")
        return False


def test_queue_setup():
    """Test RQ queue setup."""
    print_section("2. Testing RQ Queue Setup")
    
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        queue = Queue('ingestion', connection=redis_conn)
        
        print(f"✓ Queue created: {queue.name}")
        print(f"  Current jobs in queue: {queue.count}")
        return True
        
    except Exception as e:
        print(f"✗ Queue setup failed: {e}")
        return False


def test_spider_registry():
    """Test spider registry."""
    print_section("3. Testing Spider Registry")
    
    test_urls = [
        "https://www.royalroad.com/fiction/12345",
        "https://example.com/novel/test",
        "https://unknown-site.com/novel",
    ]
    
    success = True
    
    for url in test_urls:
        spider = SpiderRegistry.get_spider_for_url(url)
        is_supported = SpiderRegistry.is_supported(url)
        
        if spider:
            print(f"✓ {url}")
            print(f"  → Spider: {spider}")
        else:
            print(f"✗ {url}")
            print(f"  → Not supported")
            if "royalroad" in url or "example" in url:
                success = False
    
    return success


def test_enqueue_job():
    """Test job enqueueing."""
    print_section("4. Testing Job Enqueueing")
    
    # Create a test job
    db = SessionLocal()
    
    try:
        # Use a test URL that won't actually be processed
        test_url = "https://example.com/test-novel"
        
        # Create job
        job = IngestionJob(
            source_url=test_url,
            status=IngestionStatus.QUEUED
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        print(f"✓ Created test job: {job.id}")
        
        # Enqueue to Redis
        queue = IngestionQueue()
        success = queue.enqueue_job(job.id)
        
        if success:
            print(f"✓ Job {job.id} enqueued to Redis")
            
            # Check queue
            redis_conn = Redis.from_url(settings.redis_url)
            rq_queue = Queue('ingestion', connection=redis_conn)
            print(f"  Queue length: {rq_queue.count}")
            
            return job.id
        else:
            print(f"✗ Failed to enqueue job {job.id}")
            return None
            
    except Exception as e:
        print(f"✗ Enqueue test failed: {e}")
        return None
        
    finally:
        db.close()


def test_worker_check():
    """Check if workers are running."""
    print_section("5. Checking for Workers")
    
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        
        # Get worker keys
        worker_keys = redis_conn.keys('rq:worker:*')
        
        if worker_keys:
            print(f"✓ Found {len(worker_keys)} worker(s)")
            for key in worker_keys:
                print(f"  - {key.decode()}")
            return True
        else:
            print("⚠ No workers found")
            print("\nStart a worker in another terminal:")
            print("  python worker.py")
            return False
            
    except Exception as e:
        print(f"✗ Worker check failed: {e}")
        return False


def test_queue_monitoring():
    """Test queue monitoring."""
    print_section("6. Queue Monitoring")
    
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        
        # Queue stats
        queue_length = redis_conn.llen('rq:queue:ingestion')
        failed_length = redis_conn.llen('rq:queue:failed')
        
        print(f"✓ Queue statistics:")
        print(f"  - Pending jobs: {queue_length}")
        print(f"  - Failed jobs: {failed_length}")
        
        # Show all RQ keys
        rq_keys = redis_conn.keys('rq:*')
        print(f"  - Total RQ keys: {len(rq_keys)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Monitoring test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  Redis Queue System - Test Suite")
    print("=" * 60)
    
    all_passed = True
    
    # Test 1: Redis connection
    if not test_redis_connection():
        print("\n❌ Redis not available. Cannot continue.")
        sys.exit(1)
    
    # Test 2: Queue setup
    if not test_queue_setup():
        all_passed = False
    
    # Test 3: Spider registry
    if not test_spider_registry():
        all_passed = False
    
    # Test 4: Enqueue job
    job_id = test_enqueue_job()
    if not job_id:
        all_passed = False
    
    # Test 5: Worker check
    has_workers = test_worker_check()
    
    # Test 6: Monitoring
    if not test_queue_monitoring():
        all_passed = False
    
    # Final results
    print_section("Test Results")
    
    if all_passed:
        print("✓ All tests passed!")
        
        if has_workers:
            print("\n✅ System is ready!")
            print("\nYou can now:")
            print("  1. Start the API: python main.py")
            print("  2. Send ingestion requests")
            print("  3. Monitor with: rq info")
        else:
            print("\n⚠ System ready, but no workers running")
            print("\nStart workers:")
            print("  python worker.py")
    else:
        print("✗ Some tests failed")
        print("\nPlease fix errors above")
    
    if job_id:
        print(f"\n💡 Test job {job_id} is in queue")
        print("If a worker is running, it will process this job")
        print(f"Check status with:")
        print(f"  curl http://localhost:8000/jobs/{job_id}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
