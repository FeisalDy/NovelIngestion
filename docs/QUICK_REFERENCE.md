# Quick Reference: Redis Queue System

## 🚀 Quick Start

```bash
# 1. Install Redis
sudo apt install redis-server  # Ubuntu
brew install redis             # macOS

# 2. Start Redis
redis-server

# 3. Start API (Terminal 1)
python main.py

# 4. Start Worker (Terminal 2)
python worker.py
```

## 📝 Common Commands

### Ingest a Novel
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.royalroad.com/fiction/12345"}'
```

### Check Job Status
```bash
curl http://localhost:8000/jobs/{job_id}
```

### Monitor Queue
```bash
# Queue length
redis-cli LLEN rq:queue:ingestion

# Queue info
rq info --url redis://localhost:6379/0

# Watch workers
rq info -W --url redis://localhost:6379/0
```

### Start Multiple Workers
```bash
# Terminal 1
python worker.py

# Terminal 2
python worker.py

# Terminal 3
python worker.py
```

## 🔍 Debugging

### Check Redis Connection
```bash
redis-cli ping
# Expected: PONG
```

### View Queue Contents
```bash
# Show all keys
redis-cli KEYS "rq:*"

# Show queue length
redis-cli LLEN rq:queue:ingestion

# Show failed jobs
redis-cli LLEN rq:queue:failed
```

### Clear Queue
```bash
# Clear ingestion queue
redis-cli DEL rq:queue:ingestion

# Clear failed jobs
redis-cli DEL rq:queue:failed
```

### Re-enqueue DB Jobs
```bash
# Enqueue all QUEUED jobs
python cli.py process-queue
```

## 📊 Job States

1. **QUEUED** - Created in DB, pushed to Redis
2. **CRAWLING** - Worker running Scrapy
3. **PARSING** - Content being parsed
4. **SAVING** - Data being saved to DB
5. **DONE** - ✓ Complete
6. **ERROR** - ✗ Failed (see error_message)

## 🛠️ Production

### Supervisor Config
```ini
[program:novel-worker]
command=/path/to/venv/bin/python worker.py
directory=/path/to/novel-ingestion
numprocs=3
autostart=true
autorestart=true
```

```bash
sudo supervisorctl start novel-worker:*
```

### Systemd
```bash
# Start 3 workers
sudo systemctl start novel-worker@{1..3}

# Check status
sudo systemctl status novel-worker@1

# View logs
journalctl -u novel-worker@1 -f
```

## 🎛️ Environment Variables

```env
# Required
REDIS_URL=redis://localhost:6379/0

# Optional (with auth)
REDIS_URL=redis://:password@localhost:6379/0
```

## 📈 Performance

### Worker Count
- **I/O-bound**: 2-4 workers per CPU core
- **CPU-bound**: 1 worker per core

### Check CPU Cores
```bash
nproc
```

## 🔧 Troubleshooting

### Workers not processing?
```bash
# 1. Check Redis
redis-cli ping

# 2. Check workers running
ps aux | grep worker.py

# 3. Check queue has jobs
redis-cli LLEN rq:queue:ingestion

# 4. Check worker logs
tail -f worker.log
```

### Jobs stuck in CRAWLING?
```bash
# Find hung jobs in DB
python cli.py list-jobs

# Manually reset job
# (Update status in DB, re-enqueue)
```

### Out of memory?
```bash
# Check Redis memory
redis-cli INFO memory

# Set max memory in /etc/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

## 📚 Documentation

- **REDIS_SETUP.md** - Complete setup guide
- **REFACTORING_SUMMARY.md** - Architecture details
- **README.md** - Main documentation

## 💡 Tips

1. **Always run at least one worker** - API just enqueues
2. **Scale workers for throughput** - More workers = more parallel jobs
3. **Monitor queue length** - If growing, add workers
4. **Check failed jobs regularly** - `rq info`
5. **Use RQ dashboard for visibility** - `rq-dashboard`

## 🚨 Emergency Commands

### Kill all workers
```bash
pkill -f worker.py
```

### Flush Redis (⚠️ DANGER)
```bash
redis-cli FLUSHDB
```

### Stop Redis
```bash
sudo systemctl stop redis
# or
redis-cli SHUTDOWN
```

## 🎯 Code Locations

| Component | File | Line |
|-----------|------|------|
| Enqueue job | `ingestion_queue.py` | `enqueue_job()` |
| Process job | `ingestion_queue.py` | `process_job()` |
| Worker script | `worker.py` | `main()` |
| API endpoint | `main.py` | `/ingest` |
| Spider registry | `ingestion_queue.py` | `SpiderRegistry` |
| Crawler runner | `ingestion_queue.py` | `CrawlerRunner` |

## 🧪 Testing

```python
# Test Redis connection
from redis import Redis
redis_conn = Redis.from_url('redis://localhost:6379/0')
redis_conn.ping()  # Should return True

# Test RQ
from rq import Queue
queue = Queue('ingestion', connection=redis_conn)
print(queue.count)  # Number of jobs

# Enqueue test job
queue.enqueue('ingestion_queue.process_job', 1)
```

## 📞 Need Help?

Check logs in order:
1. Worker output (`python worker.py`)
2. API logs (`python main.py`)
3. Redis logs (`/var/log/redis/redis-server.log`)
4. Database (check job status)
