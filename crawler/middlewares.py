"""Scrapy middlewares for error handling and retries."""
from scrapy import signals
from scrapy.exceptions import IgnoreRequest
import logging

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware:
    """Middleware for graceful error handling."""
    
    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_error, signal=signals.spider_error)
        return middleware
    
    def spider_error(self, failure, response, spider):
        """Handle spider errors without killing the entire crawl."""
        logger.error(f"Spider error in {spider.name}: {failure.value}")
        logger.error(f"URL: {response.url}")


class RetryMiddleware:
    """Custom retry middleware with exponential backoff."""
    
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
    
    @classmethod
    def from_crawler(cls, crawler):
        max_retries = crawler.settings.getint('RETRY_TIMES', 3)
        return cls(max_retries=max_retries)
    
    def process_response(self, request, response, spider):
        """Process response and retry if needed."""
        if response.status in [500, 502, 503, 504, 408, 429]:
            retry_count = request.meta.get('retry_count', 0)
            
            if retry_count < self.max_retries:
                logger.warning(
                    f"Retrying {request.url} "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                retry_request = request.copy()
                retry_request.meta['retry_count'] = retry_count + 1
                retry_request.dont_filter = True
                return retry_request
            else:
                logger.error(
                    f"Max retries reached for {request.url}"
                )
        
        return response
    
    def process_exception(self, request, exception, spider):
        """Handle request exceptions."""
        logger.error(f"Request exception: {exception}")
        logger.error(f"URL: {request.url}")
