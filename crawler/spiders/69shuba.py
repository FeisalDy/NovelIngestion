from crawler.items import ChapterItem
from crawler.spiders.base_spider import BaseSpider


class SixNineShubaSpider(BaseSpider):
    """
    Spider for 69Shuba (69书吧).

    Site URL: https://www.69shuba.com/
    """

    name = "69shuba"
    allowed_domains = ["69shuba.com"]

    def extract_novel_metadata(self, response) -> None:
        """Extract novel metadata from 69shuba.com structure."""
        self.novel_item['title'] = response.css('div.book-info h1::text').get('').strip()
        self.novel_item['synopsis'] = response.css('div.book-intro p::text').get('').strip()

        # Extract status
        status_text = response.css('div.book-info p::text').re_first(r'状态：(\S+)')
        if status_text:
            status_text = status_text.lower()
            if '完结' in status_text:
                self.novel_item['status'] = 'completed'
            elif '连载' in status_text:
                self.novel_item['status'] = 'ongoing'
            else:
                self.novel_item['status'] = 'unknown'

        # Extract genres
        genres = response.css('div.book-info p a::text').getall()
        self.novel_item['genres'] = [g.strip() for g in genres if g.strip()]

        self.logger.info(f"Extracted novel: {self.novel_item['title']}")
        self.logger.info(f"Genres: {self.novel_item['genres']}")

    def extract_chapter_list(self, response) -> list:
        """Extract chapter list from 69shuba.com structure."""
        chapters = []

        chapter_elements = response.css('div.chapter-list ul li a')

        for idx, element in enumerate(chapter_elements, start=1):
            chapter_url = element.css('::attr(href)').get()
            chapter_title = element.css('::text').get('').strip()

            if chapter_url:
                chapter_url = response.urljoin(chapter_url)

                chapters.append({
                    'number': idx,
                    'title': chapter_title or f"Chapter {idx}",
                    'url': chapter_url,
                })

        return chapters

    def parse_chapter(self, response):
        """Parse individual chapter page from 69shuba.com structure."""
        chapter_item = ChapterItem()
        chapter_item['ingestion_job_id'] = self.job_id
        chapter_item['novel_source_url'] = self.source_url
        chapter_item['source_url'] = response.url

        # Extract chapter title
        chapter_item['title'] = response.css('div.chapter-title h1::text').get('').strip()

        # Extract chapter content
        content_paragraphs = response.css('div.chapter-content p::text').getall()
        chapter_item['content'] = '\n'.join([p.strip() for p in content_paragraphs if p.strip()])

        self.logger.info(f"Parsed chapter: {chapter_item['title']}")

        yield chapter_item
