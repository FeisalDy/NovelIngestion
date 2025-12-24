"""Base spider class for all novel crawlers."""
import scrapy
from abc import abstractmethod
from typing import Iterator, Optional
from scrapy import signals
from scrapy.exceptions import DontCloseSpider
from crawler.items import NovelItem, ChapterItem


class BaseSpider(scrapy.Spider):
    """
    Base spider that all site-specific spiders must inherit from.
    
    Provides common functionality and enforces interface for novel crawling.
    """
    
    # Must be set by child spiders
    name: str = "base"
    allowed_domains: list = []
    
    def __init__(self, url: str, job_id: int, *args, **kwargs):
        """
        Initialize spider with target URL and job ID.
        
        Args:
            url: The novel's main page URL
            job_id: Ingestion job ID for tracking
        """
        super().__init__(*args, **kwargs)
        self.start_urls = [url]
        self.source_url = url
        self.job_id = job_id
        self.novel_item = NovelItem()
        self.novel_item['ingestion_job_id'] = job_id
        self.novel_item['source_url'] = url
        self.novel_item['chapters'] = []
        self._item_yielded = False
    
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Connect signals."""
        spider = super(BaseSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signal=signals.spider_idle)
        return spider
        
    def parse(self, response):
        """
        Main entry point - parse the novel's main page.
        
        Must extract:
        - Novel title
        - Synopsis
        - Status (ongoing/completed)
        - Genres
        - Chapter list (urls and titles)
        
        Then yield requests to parse each chapter.
        """
        self.logger.info(f"Parsing novel main page: {response.url}")
        
        # Extract novel-level metadata
        self.extract_novel_metadata(response)
        
        # Extract chapter list and queue chapter parsing
        chapter_urls = self.extract_chapter_list(response)
        
        self.logger.info(f"Found {len(chapter_urls)} chapters for novel")
        
        # Parse each chapter
        for chapter_data in chapter_urls:
            yield scrapy.Request(
                url=chapter_data['url'],
                callback=self.parse_chapter,
                meta={
                    'chapter_number': chapter_data['number'],
                    'chapter_title': chapter_data['title'],
                },
                errback=self.handle_chapter_error,
            )
    
    @abstractmethod
    def extract_novel_metadata(self, response) -> None:
        """
        Extract novel-level metadata from main page.
        
        Must populate:
        - self.novel_item['title']
        - self.novel_item['synopsis']
        - self.novel_item['status']
        - self.novel_item['genres']
        
        Args:
            response: Scrapy response object for novel main page
        """
        pass
    
    @abstractmethod
    def extract_chapter_list(self, response) -> list:
        """
        Extract list of chapters from main page.
        
        Args:
            response: Scrapy response object for novel main page
            
        Returns:
            List of dicts with keys: 'number', 'title', 'url'
        """
        pass
    
    @abstractmethod
    def parse_chapter(self, response):
        """
        Parse individual chapter content.
        
        Must extract clean chapter content and create ChapterItem.
        
        Args:
            response: Scrapy response object for chapter page
        """
        pass
    
    def handle_chapter_error(self, failure):
        """
        Handle chapter parsing errors gracefully.
        
        Log error but don't fail entire novel ingestion.
        """
        self.logger.error(f"Chapter parsing failed: {failure.value}")
        self.logger.error(f"URL: {failure.request.url}")
        
        # Extract chapter info from request meta
        chapter_num = failure.request.meta.get('chapter_number', 'unknown')
        self.logger.warning(f"Skipping chapter {chapter_num} due to error")
    
    def spider_idle(self, spider):
        """
        Called when spider becomes idle (no more requests to process).
        
        This is where we yield the final novel item with all chapters.
        """
        # Only yield once
        if self._item_yielded:
            return
            
        self.logger.info(f"=== Spider idle - all chapters collected ===")
        self.logger.info(f"Total chapters collected: {len(self.novel_item.get('chapters', []))}")
        
        # Validate we have complete data
        if self.novel_item.get('title') and self.novel_item.get('chapters'):
            self.logger.info(f"✓ Yielding novel item to pipelines:")
            self.logger.info(f"  - Title: {self.novel_item['title']}")
            self.logger.info(f"  - Chapters: {len(self.novel_item['chapters'])}")
            self.logger.info(f"  - Job ID: {self.novel_item['ingestion_job_id']}")
            
            # Yield the item through the crawler engine
            self.crawler.engine.crawl(
                scrapy.Request(
                    url=self.source_url,
                    callback=self._yield_novel_item,
                    dont_filter=True,
                    priority=1000  # High priority to process immediately
                ),
                self
            )
            self._item_yielded = True
            raise DontCloseSpider()  # Keep spider alive to process the yielding request
        else:
            self.logger.error("✗ No valid novel data collected - not yielding to pipelines")
            self.logger.error(f"  - Has title: {bool(self.novel_item.get('title'))}")
            self.logger.error(f"  - Chapter count: {len(self.novel_item.get('chapters', []))}")
    
    def _yield_novel_item(self, response):
        """Helper callback to yield the novel item."""
        self.logger.info("=== Yielding novel item to pipeline ===")
        yield self.novel_item
    
    def closed(self, reason):
        """Called when spider closes."""
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Final chapter count: {len(self.novel_item.get('chapters', []))}")
