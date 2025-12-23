# Redis Queue Refactoring Summary

## Overview

Successfully refactored the novel ingestion system from **synchronous execution** to **Redis-based background job queue
** using RQ (Redis Queue).

## Changes Made

### 1. Updated Files

#### `ingestion_queue.py` (Refactored)

**Before:**

- `IngestionQueue` ran spiders synchronously
- `enqueue_job()` blocked until spider completed
- No background processing

**After:**

- Added Redis connection and RQ Queue setup
- `enqueue_job()` pushes job_id to Redis (non-blocking)
- New `process_job()` function for workers to call
- Workers execute `CrawlerRunner.run_spider()` in background

**Key Changes:**

```python
# Redis setup (top of file)
from redis import Redis
from rq import Queue

redis_conn = Redis.from_url(settings.redis_url)
job_queue = Queue('ingestion', connection=redis_conn)

# Enqueue to Redis (non-blocking)
self.queue.enqueue(
    'ingestion_queue.process_job',
    job_id,
    job_timeout='1h',
)

# Worker function
def process_job(job_id: int):
    """Called by RQ workers to process jobs."""
    # ... existing spider execution logic
```

#### `main.py` (Minor Change)

**Before:**

```python
crawler_runner = CrawlerRunner(settings.scrapy_project_path)
ingestion_queue = IngestionQueue(crawler_runner)
```

**After:**

```python
ingestion_queue = IngestionQueue()  # No crawler needed
```

API now only enqueues jobs - workers handle execution.

#### `requirements.txt` (Updated)

Changed from:

```
# Job Queue (Optional)
redis==5.0.1
rq==1.16.1
```

To:

```
# Job Queue (Required)
redis==5.0.1
rq==1.16.1
```

### 2. New Files

#### `worker.py` (New)

Standalone worker script that:

- Connects to Redis
- Creates RQ Worker listening to 'ingestion' queue
- Processes jobs by calling `process_job(job_id)`
- Can run multiple instances for parallel processing

**Usage:**

```bash
python worker.py
```

#### `REDIS_SETUP.md` (New)

Comprehensive guide covering:

- Architecture flow diagram
- Redis installation (Ubuntu, macOS, Docker)
- Configuration examples
- Running workers (single, multiple, production)
- Monitoring and troubleshooting
- Production deployment (Supervisor, systemd, Docker)
- Performance tuning

### 3. Updated Documentation

#### `README.md` (Updated)

- Added Redis to Quick Start steps
- Updated architecture diagram
- Added Redis + RQ to tech stack
- Added worker.py to project structure
- Updated production considerations

## Job Flow (After Refactoring)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. API Request: POST /ingest                                │
│    - Create IngestionJob in PostgreSQL (status=QUEUED)     │
│    - Push job_id to Redis queue                             │
│    - Return immediately (non-blocking)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Redis Queue (rq:queue:ingestion)                         │
│    - Stores job_id in Redis list                            │
│    - Persists across restarts                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. RQ Worker (worker.py)                                     │
│    - BLPOP from Redis (blocking pop)                        │
│    - Call process_job(job_id)                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. process_job() function                                   │
│    - Fetch job from PostgreSQL                              │
│    - Get spider name from SpiderRegistry                    │
│    - Create CrawlerRunner                                   │
│    - Execute: crawler_runner.run_spider(...)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. CrawlerRunner.run_spider()                                │
│    - Update status: CRAWLING                                │
│    - Run Scrapy via subprocess                              │
│    - Scrapy pipelines save to PostgreSQL                    │
│    - Update status: DONE or ERROR                           │
└─────────────────────────────────────────────────────────────┘
```

## Components Unchanged

✅ **SpiderRegistry** - No changes (URL → spider resolution)  
✅ **CrawlerRunner** - No changes (subprocess Scrapy execution)  
✅ **Scrapy spiders** - No changes (site-specific parsing)  
✅ **Scrapy pipelines** - No changes (normalization, DB saves)  
✅ **Database models** - No changes (same schema)  
✅ **API endpoints** - No changes (same interface)

## Configuration Required

Add to `.env`:

```env
REDIS_URL=redis://localhost:6379/0
```

## Running the System

### 1. Start Redis

```bash
redis-server
```

### 2. Start API

```bash
python main.py
```

### 3. Start Worker(s)

```bash
# Terminal 1
python worker.py

# Terminal 2 (optional, for parallel processing)
python worker.py

# Terminal 3 (optional)
python worker.py
```

## Benefits

### Before (Synchronous)

- ❌ API blocks until spider completes (slow)
- ❌ Single job at a time
- ❌ Timeout issues for long crawls
- ❌ No retry mechanism
- ❌ Jobs lost on restart

### After (Redis Queue)

- ✅ API returns immediately (fast)
- ✅ Multiple jobs in parallel (scale with workers)
- ✅ Workers handle long-running jobs
- ✅ RQ built-in retry support
- ✅ Jobs persist in Redis (survive restarts)
- ✅ Easy monitoring (RQ dashboard, CLI tools)
- ✅ Production-ready (Supervisor, systemd support)

## Testing

### Test 1: Enqueue Job

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.royalroad.com/fiction/12345"}'
```

**Expected:**

- Returns immediately with `job_id`
- Job status: `QUEUED`

### Test 2: Worker Processing

```bash
# In worker terminal, you should see:
# Worker processing job 1
# Running spider 'royalroad' for job 1
# Job 1 processing completed: True
```

### Test 3: Check Status

```bash
curl http://localhost:8000/jobs/1
```

**Expected progression:**

1. `QUEUED` - Just created
2. `CRAWLING` - Worker picked up
3. `PARSING` - Content being parsed
4. `SAVING` - Data being saved
5. `DONE` - Complete

### Test 4: Monitor Queue

```bash
# Check queue length
redis-cli LLEN rq:queue:ingestion

# Show queue info
rq info --url redis://localhost:6379/0
```

## Production Deployment

### Option 1: Supervisor (Recommended)

`/etc/supervisor/conf.d/novel-worker.conf`:

```ini
[program:novel-worker]
command=/path/to/venv/bin/python /path/to/worker.py
directory=/path/to/novel-ingestion
numprocs=3
process_name=%(program_name)s_%(process_num)02d
autostart=true
autorestart=true
stopasgroup=true
```

Start:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start novel-worker:*
```

### Option 2: Systemd

`/etc/systemd/system/novel-worker@.service`:

```ini
[Unit]
Description=Novel Ingestion Worker %i

[Service]
Type=simple
WorkingDirectory=/path/to/novel-ingestion
ExecStart=/path/to/venv/bin/python worker.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Start 3 workers:

```bash
sudo systemctl start novel-worker@{1..3}
sudo systemctl enable novel-worker@{1..3}
```

### Option 3: Docker

See `REDIS_SETUP.md` for complete Docker Compose example.

## Monitoring

### RQ Dashboard (Web UI)

```bash
pip install rq-dashboard
rq-dashboard --redis-url redis://localhost:6379/0
```

Visit: `http://localhost:9181`

### CLI Monitoring

```bash
# Queue status
rq info --url redis://localhost:6379/0

# Worker status
rq info -W --url redis://localhost:6379/0

# Failed jobs
redis-cli LLEN rq:queue:failed
```

### Application Logs

Workers log to stdout:

```bash
# With systemd
journalctl -u novel-worker@1 -f

# With supervisor
tail -f /var/log/novel-worker.log
```

## Troubleshooting

### Jobs not processing

```bash
# 1. Check Redis is running
redis-cli ping
# Should return: PONG

# 2. Check workers are running
ps aux | grep worker.py

# 3. Check queue length
redis-cli LLEN rq:queue:ingestion

# 4. Check for errors in worker logs
tail -f worker.log
```

### Clear stuck jobs

```bash
# Clear queue
redis-cli DEL rq:queue:ingestion

# Clear failed jobs
redis-cli DEL rq:queue:failed
```

### Re-enqueue DB jobs

```bash
python cli.py process-queue
```

This will enqueue all jobs in DB with status `QUEUED`.

## Migration Notes

The refactoring is **backwards compatible** for the API:

- POST `/ingest` behaves the same (just faster)
- All read endpoints unchanged
- Database schema unchanged
- Existing novels/chapters unaffected

Only operational change: **Workers must be running** to process jobs.

## Performance Recommendations

**Worker Count:**

- **I/O-bound** (Scrapy): 2-4 workers per CPU core
- **CPU-bound**: 1 worker per core

**Timeouts:**

- Default: 1 hour per job
- Adjust in `ingestion_queue.py` if needed

**Redis Memory:**

- Monitor with: `redis-cli INFO memory`
- Set `maxmemory` in `/etc/redis/redis.conf`

**Job TTL:**

- Results kept 24 hours: `result_ttl=86400`
- Failures kept 7 days: `failure_ttl=604800`
- Adjust in `enqueue_job()` if needed

## Code Quality

- ✅ No breaking changes to existing code
- ✅ Minimal modifications (surgical changes)
- ✅ Backwards compatible API
- ✅ Clear separation of concerns
- ✅ Production-ready patterns
- ✅ Comprehensive documentation

## Next Steps

1. ✅ Install Redis
2. ✅ Update `.env` with `REDIS_URL`
3. ✅ Run `pip install -r requirements.txt`
4. ✅ Start workers: `python worker.py`
5. ✅ Start API: `python main.py`
6. ✅ Test ingestion endpoint

## Support

For detailed setup and deployment instructions, see:

- [REDIS_SETUP.md](REDIS_SETUP.md) - Complete Redis guide
- [README.md](../README.md) - Main documentation
