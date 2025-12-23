# Architecture Comparison: Before vs After

## BEFORE: Synchronous Execution

```
┌──────────────────────────────────────────────────────────────┐
│                     API Request                              │
│                  POST /ingest {url}                          │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│               Create IngestionJob                            │
│            (PostgreSQL, status=QUEUED)                       │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│         IngestionQueue.enqueue_job(job_id)                   │
│              ⚠️  BLOCKS HERE ⚠️                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│         CrawlerRunner.run_spider(...)                        │
│         - Update status to CRAWLING                          │
│         - Run Scrapy via subprocess                          │
│         - Wait for completion (minutes to hours)             │
│         - Update status to DONE or ERROR                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼ (FINALLY!)
┌──────────────────────────────────────────────────────────────┐
│               Return Response                                │
│         {job_id: 1, status: "done"}                          │
└──────────────────────────────────────────────────────────────┘

Problems:
❌ API blocks for entire crawl duration
❌ Request timeout for long novels
❌ Single job at a time (no parallelism)
❌ No retry mechanism
❌ Jobs lost on server restart
```

## AFTER: Redis Queue with Background Workers

```
┌──────────────────────────────────────────────────────────────┐
│                     API Request                              │
│                  POST /ingest {url}                          │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│               Create IngestionJob                            │
│            (PostgreSQL, status=QUEUED)                       │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│         IngestionQueue.enqueue_job(job_id)                   │
│         - Push job_id to Redis queue                         │
│         - RQ: queue.enqueue('process_job', job_id)           │
│         ✅  RETURNS IMMEDIATELY  ✅                           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼ (< 100ms)
┌──────────────────────────────────────────────────────────────┐
│               Return Response                                │
│         {job_id: 1, status: "queued"}                        │
└──────────────────────────────────────────────────────────────┘


Meanwhile, in parallel:

┌──────────────────────────────────────────────────────────────┐
│               Redis Queue                                     │
│         rq:queue:ingestion                                   │
│         [job_id: 1, job_id: 2, ...]                          │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼ (BLPOP - blocking pop)
┌──────────────────────────────────────────────────────────────┐
│         RQ Worker #1 (worker.py)                             │
│         - Pop job_id from Redis                              │
│         - Call process_job(job_id)                           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│         process_job(job_id)                                  │
│         - Fetch job from PostgreSQL                          │[worker.py](worker.py)
│         - Get spider from SpiderRegistry                     │
│         - Create CrawlerRunner                               │
│         - Execute: run_spider(...)                           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│         CrawlerRunner.run_spider(...)                        │
│         - Update status to CRAWLING                          │
│         - Run Scrapy via subprocess                          │
│         - Scrapy pipelines save to PostgreSQL                │
│         - Update status to DONE or ERROR                     │
└──────────────────────────────────────────────────────────────┘


User can check status anytime:

┌──────────────────────────────────────────────────────────────┐
│               GET /jobs/{job_id}                             │
│         Returns current status:                              │
│         - QUEUED → waiting in Redis                          │
│         - CRAWLING → worker processing                       │
│         - DONE → complete                                    │
│         - ERROR → failed (with error_message)                │
└──────────────────────────────────────────────────────────────┘

Benefits:
✅ API returns in <100ms (non-blocking)
✅ Multiple workers = parallel processing
✅ Jobs survive server restarts (Redis persistence)
✅ Built-in retry mechanism (RQ)
✅ Easy monitoring (RQ dashboard, CLI)
✅ Scalable (add workers as needed)
```

## Parallel Processing Example

With multiple workers:

```
API enqueues:          Redis Queue:          Workers:
    
POST /ingest (url1) → [job1, job2, job3] → Worker 1: job1 (crawling)
POST /ingest (url2) →                     → Worker 2: job2 (crawling)  
POST /ingest (url3) →                     → Worker 3: job3 (crawling)
    ⬇ (immediate)                              ⬇ (parallel)
  Returns                                   All running
  job_id: 1                                simultaneously!
  job_id: 2
  job_id: 3
```

## Code Changes Summary

### ingestion_queue.py

**Before:**

```python
class IngestionQueue:
    def __init__(self, crawler_runner: CrawlerRunner):
        self.crawler_runner = crawler_runner

    def enqueue_job(self, job_id: int) -> bool:
        # Runs synchronously (blocks)
        success = self.crawler_runner.run_spider(...)
        return success
```

**After:**

```python
# Redis setup
from redis import Redis
from rq import Queue

redis_conn = Redis.from_url(settings.redis_url)
job_queue = Queue('ingestion', connection=redis_conn)


class IngestionQueue:
    def enqueue_job(self, job_id: int) -> bool:
        # Enqueue to Redis (non-blocking)
        self.queue.enqueue(
            'ingestion_queue.process_job',
            job_id,
            job_timeout='1h'
        )
        return True


# Worker function (called by RQ workers)
def process_job(job_id: int):
    crawler_runner = CrawlerRunner(...)
    success = crawler_runner.run_spider(...)
    return success
```

### main.py

**Before:**

```python
crawler_runner = CrawlerRunner(settings.scrapy_project_path)
ingestion_queue = IngestionQueue(crawler_runner)
```

**After:**

```python
ingestion_queue = IngestionQueue()  # No crawler needed
```

### NEW: worker.py

```python
from redis import Redis
from rq import Worker, Connection

redis_conn = Redis.from_url(settings.redis_url)

with Connection(redis_conn):
    worker = Worker(['ingestion'], connection=redis_conn)
    worker.work()
```

## Running the System

### Terminal 1: Redis

```bash
redis-server
```

### Terminal 2: API

```bash
python main.py
# API listening on :8000
```

### Terminal 3: Worker(s)

```bash
python worker.py
# Worker ready. Waiting for jobs...
```

### Terminal 4: Client

```bash
curl -X POST http://localhost:8000/ingest \
  -d '{"url": "..."}'
# Returns immediately!
```

## Unchanged Components

✅ **SpiderRegistry** - Same URL → spider logic  
✅ **CrawlerRunner** - Same Scrapy subprocess execution  
✅ **Scrapy spiders** - Same site-specific parsing  
✅ **Scrapy pipelines** - Same normalization & DB saves  
✅ **Database models** - Same schema  
✅ **API endpoints** - Same interface  
✅ **Frontend** - No changes needed!

## What Changed

**Minimal, surgical changes:**

1. Added Redis connection and RQ setup
2. Made `enqueue_job()` push to Redis
3. Created `process_job()` worker function
4. Created `worker.py` script
5. Updated `main.py` (1 line)

**That's it!** Everything else works exactly the same.
