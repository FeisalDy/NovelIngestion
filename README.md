# Novel Ingestion Backend

A Python-based backend system for crawling, ingesting, and serving web novels. Built with FastAPI, Scrapy, and PostgreSQL.

## Features

- 🕷️ **Site-specific web crawling** with Scrapy
- 📚 **Novel metadata extraction** (title, synopsis, status, genres)
- 📖 **Chapter content normalization** (clean HTML, no ads)
- 🏷️ **First-class genre support** with normalization
- 🔄 **Asynchronous ingestion** with job tracking
- 🚀 **Read-only REST API** for frontend consumption
- 🗄️ **PostgreSQL storage** with SQLAlchemy ORM
- 📊 **Pagination** for all list endpoints

## Architecture

```
┌─────────────────┐
│   FastAPI       │  POST /ingest → Create job
│   (API Layer)   │  GET /novels → Read data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Ingestion Queue │  Manage crawl jobs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Scrapy      │  Site-specific spiders
│   (Crawlers)    │  Extract structured data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Normalizer     │  Clean HTML, compute words
│   (Pipelines)   │  Normalize genres
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │  Store novels, chapters, genres
└─────────────────┘
```

## Technology Stack

- **Python 3.11+**
- **FastAPI** - Modern async web framework
- **Scrapy** - Web crawling and scraping
- **PostgreSQL** - Primary database
- **SQLAlchemy** - ORM with async support
- **Alembic** - Database migrations
- **BeautifulSoup4** - HTML parsing and cleaning
- **Pydantic** - Data validation

## Project Structure

```
novel-ingestion/
├── main.py                 # FastAPI application
├── config.py              # Application configuration
├── database.py            # Database setup and sessions
├── models.py              # SQLAlchemy models
├── schemas.py             # Pydantic schemas
├── normalizer.py          # Content cleaning and normalization
├── ingestion_queue.py     # Job queue and crawler management
├── requirements.txt       # Python dependencies
├── alembic.ini           # Alembic configuration
├── alembic/              # Database migrations
│   └── env.py
└── crawler/              # Scrapy project
    ├── scrapy.cfg
    └── crawler/
        ├── settings.py
        ├── items.py
        ├── pipelines.py
        ├── middlewares.py
        └── spiders/
            ├── base_spider.py       # Base spider class
            └── example_spiders.py   # Site-specific implementations
```

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required settings:**
- `DATABASE_URL` - PostgreSQL connection string
- `DATABASE_URL_SYNC` - Sync version for Alembic/Scrapy

### 3. Initialize Database

```bash
# Run migrations to create tables
alembic upgrade head
```

### 4. Start the API Server

```bash
# Development mode with auto-reload
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at: `http://localhost:8000`

Interactive docs at: `http://localhost:8000/docs`

## Usage

### Ingest a Novel

```bash
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.royalroad.com/fiction/12345"}'
```

Response:
```json
{
  "job_id": 1,
  "status": "queued",
  "message": "Ingestion job created and queued"
}
```

### Check Job Status

```bash
curl "http://localhost:8000/jobs/1"
```

### List Novels

```bash
# All novels
curl "http://localhost:8000/novels?page=1&page_size=20"

# Search novels
curl "http://localhost:8000/novels?search=dragon"

# Filter by genre
curl "http://localhost:8000/novels?genre=fantasy"
```

### Get Novel Details

```bash
curl "http://localhost:8000/novels/my-novel-slug"
```

### List Chapters

```bash
curl "http://localhost:8000/novels/my-novel-slug/chapters?page=1"
```

### Read Chapter

```bash
curl "http://localhost:8000/novels/my-novel-slug/chapters/1"
```

### List Genres

```bash
curl "http://localhost:8000/genres"
```

### Novels by Genre

```bash
curl "http://localhost:8000/genres/fantasy/novels"
```

## Database Schema

### Tables

- **novels** - Novel metadata (title, synopsis, status, word count)
- **chapters** - Chapter content (number, title, clean HTML)
- **genres** - Genre definitions (name, slug)
- **novel_genres** - Many-to-many relationship
- **ingestion_jobs** - Job tracking (status, errors, timestamps)

### Relationships

- Novel → Chapters (one-to-many)
- Novel ↔ Genres (many-to-many)
- Job tracks ingestion progress

## Adding New Site Spiders

### 1. Create Spider Class

Create a new spider in `crawler/crawler/spiders/`:

```python
from crawler.spiders.base_spider import BaseSpider
from crawler.items import ChapterItem

class MySiteSpider(BaseSpider):
    name = "mysite"
    allowed_domains = ["mysite.com"]
    
    def extract_novel_metadata(self, response):
        self.novel_item['title'] = response.css('h1.title::text').get()
        self.novel_item['synopsis'] = response.css('.synopsis::text').get()
        self.novel_item['status'] = 'ongoing'
        self.novel_item['genres'] = response.css('.genre::text').getall()
    
    def extract_chapter_list(self, response):
        chapters = []
        for idx, link in enumerate(response.css('a.chapter'), 1):
            chapters.append({
                'number': idx,
                'title': link.css('::text').get(),
                'url': response.urljoin(link.css('::attr(href)').get())
            })
        return chapters
    
    def parse_chapter(self, response):
        content = response.css('.chapter-content').get()
        chapter_item = ChapterItem(
            chapter_number=response.meta['chapter_number'],
            chapter_title=response.meta['chapter_title'],
            chapter_url=response.url,
            content=content
        )
        self.novel_item['chapters'].append(dict(chapter_item))
```

### 2. Register Domain

Update `ingestion_queue.py`:

```python
DOMAIN_SPIDER_MAP = {
    'mysite.com': 'mysite',
    'www.mysite.com': 'mysite',
    # ... other domains
}
```

## Content Normalization

The system automatically:

1. **Cleans HTML** - Removes scripts, ads, navigation
2. **Normalizes formatting** - Consistent paragraph spacing
3. **Generates slugs** - URL-safe identifiers
4. **Counts words** - Per chapter and total
5. **Normalizes genres** - Consistent genre slugs

### Allowed HTML Tags

Chapters support: `p`, `br`, `em`, `strong`, `b`, `i`, `u`, `h1-h6`, `blockquote`, `ol`, `ul`, `li`, `hr`, `span`, `div`

## Genre System

Genres are first-class entities:

- **Raw genres** scraped from source sites
- **Normalized** to consistent slugs (e.g., "Sci-Fi" → "science-fiction")
- **Deduplicated** globally across all novels
- **Many-to-many** relationship with novels

Example genre mappings:
- "Fantasy" → `fantasy`
- "Sci-Fi", "Science Fiction" → `science-fiction`
- "Slice of Life" → `slice-of-life`

## API Endpoints

### Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingest` | Create ingestion job |
| GET | `/jobs/{job_id}` | Get job status |

### Novels

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/novels` | List novels (paginated) |
| GET | `/novels/{slug}` | Get novel details |

### Chapters

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/novels/{slug}/chapters` | List chapters (paginated) |
| GET | `/novels/{slug}/chapters/{number}` | Get chapter content |

### Genres

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/genres` | List all genres |
| GET | `/genres/{slug}` | Get genre details |
| GET | `/genres/{slug}/novels` | List novels by genre |

## Configuration

All settings in `.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
DATABASE_URL_SYNC=postgresql://user:pass@localhost/dbname

# API
API_HOST=0.0.0.0
API_PORT=8000

# Pagination
DEFAULT_PAGE_SIZE=20
MAX_PAGE_SIZE=100

# Logging
LOG_LEVEL=INFO
```

## Error Handling

- **Partial progress** - Failed chapters don't fail entire novel
- **Job tracking** - All errors logged per job
- **Retry support** - Jobs can be re-run
- **Graceful degradation** - Missing data handled safely

## Database Migrations

### Create Migration

```bash
alembic revision --autogenerate -m "Description of changes"
```

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback

```bash
alembic downgrade -1
```

## Development

### Run Tests

```bash
pytest
```

### Format Code

```bash
black .
```

### Lint

```bash
flake8 .
```

## Production Considerations

### Background Job Queue

For production, replace synchronous job processing with:

- **Redis + RQ** - Simple Python job queue
- **Celery** - Distributed task queue
- **Cloud services** - AWS SQS, Google Cloud Tasks

### Scaling

- Run multiple worker processes for job processing
- Use connection pooling for database
- Add caching layer (Redis) for read endpoints
- Consider read replicas for heavy read traffic

### Monitoring

- Add structured logging (JSON format)
- Integrate application monitoring (Sentry, DataDog)
- Track job success/failure rates
- Monitor crawler performance

## License

MIT

## Support

For issues or questions, please open a GitHub issue.
