# Redis Queue Setup Guide

## Overview

The ingestion system now uses **Redis + RQ (Redis Queue)** for background job processing.

## Architecture Flow

```
┌──────────────┐
│   FastAPI    │  1. Create IngestionJob in DB
│   (API)      │  2. Push job_id to Redis queue
└──────┬───────┘  3. Return immediately
       │
       ▼
┌──────────────┐
│    Redis     │  Job queue storage
│   (Queue)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  RQ Worker   │  4. Pop job from Redis
│  (worker.py) │  5. Call CrawlerRunner.run_spider()
└──────┬───────┘  6. Update DB status
       │
       ▼
┌──────────────┐
│  PostgreSQL  │  Job status + novel data
└──────────────┘
```

## Installation

### 1. Install Redis

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**macOS (Homebrew):**

```bash
brew install redis
brew services start redis
```

**Docker:**

```bash
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

### 2. Verify Redis is Running

```bash
redis-cli ping
# Expected output: PONG
```

## Configuration

Update your `.env` file:

```env
REDIS_URL=redis://localhost:6379/0
```

For production with authentication:

```env
REDIS_URL=redis://:password@localhost:6379/0
```

## Running the System

### 1. Start the API Server

```bash
python main.py
```

API will be available at `http://localhost:8000`

### 2. Start Worker(s)

**Single worker:**

```bash
python worker.py
```

**Multiple workers (for parallel processing):**

```bash
# Terminal 1
python worker.py

# Terminal 2
python worker.py

# Terminal 3
python worker.py
```

**Or using RQ directly:**

```bash
rq worker ingestion --url redis://localhost:6379/0
```

### 3. Monitor Queue

**RQ Dashboard (optional):**

```bash
pip install rq-dashboard
rq-dashboard --redis-url redis://localhost:6379/0
```

Visit `http://localhost:9181` for web UI.

**CLI monitoring:**

```bash
# Show queue status
rq info --url redis://localhost:6379/0

# Show workers
rq info --url redis://localhost:6379/0 -W
```

## Usage Example

### Enqueue a Job

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.royalroad.com/fiction/12345"}'
```

Response (immediate):

```json
{
  "job_id": 42,
  "status": "queued",
  "message": "Ingestion job created and queued"
}
```

### Check Job Status

```bash
curl http://localhost:8000/jobs/42
```

Response:

```json
{
  "id": 42,
  "source_url": "https://www.royalroad.com/fiction/12345",
  "status": "crawling",
  "error_message": null,
  "created_at": "2025-12-23T10:30:00",
  "updated_at": "2025-12-23T10:30:15"
}
```

## Job Lifecycle

1. **QUEUED** - Job created in DB, pushed to Redis
2. **CRAWLING** - Worker picked up job, Scrapy running
3. **PARSING** - Content being parsed
4. **SAVING** - Data being saved to DB
5. **DONE** - ✓ Complete
6. **ERROR** - ✗ Failed (with error_message)

## Production Deployment

### Supervisor (Process Manager)

Create `/etc/supervisor/conf.d/novel-worker.conf`:

```ini
[program:novel-worker]
command = /path/to/venv/bin/python /path/to/worker.py
directory = /path/to/novel-ingestion
user = www-data
numprocs = 3
process_name = %(program_name)s_%(process_num)02d
autostart = true
autorestart = true
stopasgroup = true
killasgroup = true
stdout_logfile = /var/log/novel-worker.log
stderr_logfile = /var/log/novel-worker.err.log
```

Start workers:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start novel-worker:*
```

### Systemd Service

Create `/etc/systemd/system/novel-worker@.service`:

```ini
[Unit]
Description = Novel Ingestion Worker %i
After = network.target redis.service postgresql.service

[Service]
Type = simple
User = www-data
WorkingDirectory = /path/to/novel-ingestion
Environment = "PATH=/path/to/venv/bin"
ExecStart = /path/to/venv/bin/python worker.py
Restart = always
RestartSec = 10

[Install]
WantedBy = multi-user.target
```

Start 3 workers:

```bash
sudo systemctl start novel-worker@{1..3}
sudo systemctl enable novel-worker@{1..3}
```

### Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  api:
    build: ..
    command: python main.py
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres
    environment:
      - REDIS_URL=redis://redis:6379/0

  worker:
    build: ..
    command: python worker.py
    deploy:
      replicas: 3
    depends_on:
      - redis
      - postgres
    environment:
      - REDIS_URL=redis://redis:6379/0

volumes:
  redis-data:
```

## Troubleshooting

### Worker not processing jobs

```bash
# Check Redis connection
redis-cli ping

# Check queue contents
redis-cli LLEN rq:queue:ingestion

# Check for failed jobs
redis-cli LLEN rq:queue:failed
```

### View failed job details

```python
from redis import Redis
from rq import Queue
from rq.job import Job

redis_conn = Redis.from_url('redis://localhost:6379/0')
failed_queue = Queue('failed', connection=redis_conn)

for job_id in failed_queue.job_ids:
    job = Job.fetch(job_id, connection=redis_conn)
    print(f"Job {job_id}: {job.exc_info}")
```

### Clear queue

```bash
# Clear all jobs
redis-cli DEL rq:queue:ingestion

# Clear failed jobs
redis-cli DEL rq:queue:failed
```

## Performance Tuning

### Worker Count

Rule of thumb: **1-2 workers per CPU core**

For I/O-bound tasks (Scrapy): can run more workers

```bash
# Check CPU cores
nproc

# Run 2x workers
python worker.py &  # Repeat N times
```

### Job Timeout

Default: 1 hour per job

Adjust in `ingestion_queue.py`:

```python
self.queue.enqueue(
    'ingestion_queue.process_job',
    job_id,
    job_timeout='30m',  # 30 minutes
)
```

### Redis Memory

Monitor Redis memory:

```bash
redis-cli INFO memory
```

Configure in `/etc/redis/redis.conf`:

```
maxmemory 2gb
maxmemory-policy allkeys-lru
```

## Monitoring

### Key Metrics to Track

- Queue length: `LLEN rq:queue:ingestion`
- Active workers: `SMEMBERS rq:workers`
- Failed jobs: `LLEN rq:queue:failed`
- Job processing time
- Success/failure rates

### Logging

Workers log to stdout/stderr. Capture with:

```bash
# systemd
journalctl -u novel-worker@1 -f

# supervisor
tail -f /var/log/novel-worker.log
```

## Migration from Synchronous

The old synchronous code is automatically replaced. No migration needed.

Jobs in DB with status `QUEUED` can be enqueued via CLI:

```bash
python cli.py process-queue
```

This will push all `QUEUED` jobs to Redis.

## Benefits

✅ **Non-blocking API** - Returns immediately  
✅ **Parallel processing** - Multiple workers  
✅ **Fault tolerance** - Jobs survive restarts  
✅ **Retry support** - RQ handles retries  
✅ **Monitoring** - Built-in tools  
✅ **Scalable** - Add more workers easily  
