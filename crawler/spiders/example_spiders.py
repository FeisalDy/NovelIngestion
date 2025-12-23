"""Example site-specific spider implementation."""
import scrapy
from crawler.spiders.base_spider import BaseSpider
from crawler.items import ChapterItem


class ExampleSiteSpider(BaseSpider):
    """
    Example spider for demonstration purposes.
    
    This shows how to implement a site-specific spider.
    Replace with actual site implementations.
    """
    
    name = "example_site"
    allowed_domains = ["example.com"]
    
    def extract_novel_metadata(self, response) -> None:
        """Extract novel metadata from example.com structure."""
        # Example selectors - adjust for actual site
        self.novel_item['title'] = response.css('h1.novel-title::text').get('')
        self.novel_item['synopsis'] = response.css('div.synopsis::text').get('')
        
        # Extract status
        status_text = response.css('span.status::text').get('').lower()
        if 'completed' in status_text or 'finished' in status_text:
            self.novel_item['status'] = 'completed'
        elif 'ongoing' in status_text:
            self.novel_item['status'] = 'ongoing'
        else:
            self.novel_item['status'] = 'unknown'
        
        # Extract genres
        genres = response.css('div.genres a::text').getall()
        self.novel_item['genres'] = [g.strip() for g in genres if g.strip()]
        
        self.logger.info(f"Extracted novel: {self.novel_item['title']}")
        self.logger.info(f"Genres: {self.novel_item['genres']}")
    
    def extract_chapter_list(self, response) -> list:
        """Extract chapter list from example.com structure."""
        chapters = []
        
        # Example: chapters listed in a table or list
        chapter_elements = response.css('ul.chapter-list li')
        
        for idx, element in enumerate(chapter_elements, start=1):
            chapter_url = element.css('a::attr(href)').get()
            chapter_title = element.css('a::text').get('').strip()
            
            if chapter_url:
                # Make absolute URL
                chapter_url = response.urljoin(chapter_url)
                
                chapters.append({
                    'number': idx,
                    'title': chapter_title or f"Chapter {idx}",
                    'url': chapter_url,
                })
        
        return chapters
    
    def parse_chapter(self, response):
        """Parse chapter content from example.com."""
        chapter_number = response.meta['chapter_number']
        chapter_title = response.meta['chapter_title']
        
        # Extract chapter content
        # Example: content in a div with class 'chapter-content'
        content_paragraphs = response.css('div.chapter-content p').getall()
        content = '\n'.join(content_paragraphs)
        
        if not content:
            self.logger.warning(f"No content found for chapter {chapter_number}")
            return
        
        # Create chapter item
        chapter_item = ChapterItem()
        chapter_item['chapter_number'] = chapter_number
        chapter_item['chapter_title'] = chapter_title
        chapter_item['chapter_url'] = response.url
        chapter_item['content'] = content
        
        # Add to novel's chapter list
        self.novel_item['chapters'].append(dict(chapter_item))
        
        self.logger.debug(f"Parsed chapter {chapter_number}: {chapter_title}")


class RoyalRoadSpider(BaseSpider):
    """
    Spider for RoyalRoad.com novels.
    
    RoyalRoad is a popular web novel platform.
    """
    
    name = "royalroad"
    allowed_domains = ["royalroad.com"]
    
    def extract_novel_metadata(self, response) -> None:
        """Extract novel metadata from RoyalRoad."""
        self.novel_item['title'] = response.css('h1.font-white::text').get('').strip()
        
        # Synopsis might be in multiple paragraphs
        synopsis_parts = response.css('div.description p::text').getall()
        self.novel_item['synopsis'] = '\n'.join(p.strip() for p in synopsis_parts if p.strip())
        
        # Status
        status_badge = response.css('span.label.bg-success::text').get('').lower()
        if 'completed' in status_badge:
            self.novel_item['status'] = 'completed'
        else:
            self.novel_item['status'] = 'ongoing'
        
        # Genres from tags
        genres = response.css('span.tags a.fiction-tag::text').getall()
        self.novel_item['genres'] = [g.strip() for g in genres if g.strip()]
        
        self.logger.info(f"RoyalRoad novel: {self.novel_item['title']}")
    
    def extract_chapter_list(self, response) -> list:
        """Extract chapter list from RoyalRoad."""
        chapters = []
        
        # RoyalRoad uses a table for chapters
        chapter_rows = response.css('table#chapters tbody tr[data-url]')
        
        for idx, row in enumerate(chapter_rows, start=1):
            chapter_url = row.css('::attr(data-url)').get()
            chapter_title = row.css('a::text').get('').strip()
            
            if chapter_url:
                chapter_url = response.urljoin(chapter_url)
                
                chapters.append({
                    'number': idx,
                    'title': chapter_title or f"Chapter {idx}",
                    'url': chapter_url,
                })
        
        return chapters
    
    def parse_chapter(self, response):
        """Parse chapter content from RoyalRoad."""
        chapter_number = response.meta['chapter_number']
        chapter_title = response.meta['chapter_title']
        
        # RoyalRoad chapter content
        content_div = response.css('div.chapter-content')
        
        if not content_div:
            self.logger.warning(f"No content div for chapter {chapter_number}")
            return
        
        # Get all paragraphs as HTML to preserve formatting
        content = content_div.get()
        
        chapter_item = ChapterItem()
        chapter_item['chapter_number'] = chapter_number
        chapter_item['chapter_title'] = chapter_title
        chapter_item['chapter_url'] = response.url
        chapter_item['content'] = content
        
        self.novel_item['chapters'].append(dict(chapter_item))
        
        self.logger.debug(f"RoyalRoad chapter {chapter_number} parsed")
