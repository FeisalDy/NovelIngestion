import re
from typing import Optional

import requests
import scrapy
from pydantic import BaseModel

from crawler.items import ChapterItem
from crawler.spiders.base_spider import BaseSpider


class PixivCoverUrls(BaseModel):
    original: Optional[str]


class PixivSeriesCover(BaseModel):
    urls: PixivCoverUrls


class PixivSeriesBody(BaseModel):
    id: str
    title: str
    caption: Optional[str]
    tags: Optional[list[str]]

    userId: str
    userName: str

    isConcluded: bool
    xRestrict: int  # 0 = safe, 1 = R-18

    publishedContentCount: int
    publishedTotalCharacterCount: int
    publishedTotalWordCount: int
    lastPublishedContentTimestamp: int
    createdTimestamp: int

    firstNovelId: str
    latestNovelId: str
    total: int

    cover: Optional[PixivSeriesCover]


class PixivSeriesResponse(BaseModel):
    error: bool
    message: Optional[str]
    body: PixivSeriesBody


class PixivChapterThumbnail(BaseModel):
    id: str
    title: str


class PixivThumbnails(BaseModel):
    novel: list[PixivChapterThumbnail]


class PixivSeriesContentBody(BaseModel):
    thumbnails: PixivThumbnails


class PixivSeriesContentResponse(BaseModel):
    error: bool
    message: Optional[str]
    body: PixivSeriesContentBody


class PixivTag(BaseModel):
    tag: str


class PixivTags(BaseModel):
    tags: list[PixivTag]


class PixivNovelBody(BaseModel):
    id: str
    title: str
    content: str

    tags: PixivTags

    wordCount: Optional[int] = None
    characterCount: Optional[int] = None
    readingTime: Optional[int] = None
    language: Optional[str] = None


class PixivNovelResponse(BaseModel):
    error: bool
    message: Optional[str] = None
    body: PixivNovelBody


class PixivSpider(BaseSpider):
    """
    Example spider for demonstration purposes.

    This shows how to implement a site-specific spider.
    Replace with actual site implementations.
    """

    name = "pixiv"
    allowed_domains = ["pixiv.net"]

    def __init__(self, url: str, job_id: int, *args, **kwargs):
        super().__init__(url, job_id, *args, **kwargs)
        self.series_id = None
        self.logger.info(f"Initializing PixivSpider for job {job_id}")
        self.logger.info(f"Source URL: {url}")

    def start_requests(self):
        """
        Convert website URL → Pixiv API URL
        
        This overrides Scrapy's default start_requests() to use the API URL
        instead of the regular website URL.
        """
        self.logger.info("Starting Pixiv spider...")
        self.logger.info(f"Parsing series ID from URL: {self.source_url}")

        match = re.search(r"/novel/series/(\d+)", self.source_url)
        if not match:
            error_msg = f"Invalid Pixiv novel series URL: {self.source_url}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        self.series_id = match.group(1)
        self.logger.info(f"Extracted series ID: {self.series_id}")

        api_url = f"https://www.pixiv.net/ajax/novel/series/{self.series_id}"
        self.logger.info(f"Fetching series metadata from: {api_url}")

        yield scrapy.Request(url=api_url, callback=self.parse, headers=self._pixiv_headers())

    def extract_novel_metadata(self, response) -> None:
        """Extract novel metadata from api response structure."""
        self.logger.info("Extracting novel metadata from API response...")
        self.logger.info(f"Response URL: {response.url}")
        self.logger.info(f"Response status: {response.status}")

        try:
            # Try to parse JSON
            json_data = response.json()
            self.logger.debug(f"JSON data received: {str(json_data)[:500]}...")
        except Exception as e:
            self.logger.error(f"Failed to parse response as JSON: {e}")
            self.logger.error(f"Response headers: {response.headers}")
            self.logger.error(f"Response body (first 1000 chars): {response.text[:1000]}")
            raise ValueError(f"Expected JSON response but got: {response.headers.get('Content-Type')}")

        try:
            data = PixivSeriesResponse.model_validate(json_data)
        except Exception as e:
            self.logger.error(f"Failed to validate response data: {e}")
            self.logger.error(f"JSON data: {json_data}")
            raise

        if data.error:
            error_msg = f"API returned error: {data.message}"
            self.logger.error(error_msg)
            raise scrapy.exceptions.CloseSpider(error_msg)

        body = data.body

        self.logger.info(f"Series ID: {body.id}")
        self.logger.info(f"Title: {body.title}")
        self.logger.info(f"Author: {body.userName} (ID: {body.userId})")
        self.logger.info(f"Status: {'Completed' if body.isConcluded else 'Ongoing'}")
        self.logger.info(f"Published chapters: {body.publishedContentCount}/{body.total}")
        self.logger.info(f"Total words: {body.publishedTotalWordCount}")
        self.logger.info(f"Tags: {body.tags}")

        # Example selectors - adjust for actual site
        self.novel_item['title'] = body.title
        self.novel_item['synopsis'] = body.caption
        self.novel_item['status'] = 'completed' if body.isConcluded else 'ongoing'
        self.novel_item['genres'] = body.tags

        self.logger.info(f"✓ Successfully extracted novel metadata")
        self.logger.info(f"  Title: {self.novel_item['title']}")
        self.logger.info(f"  Status: {self.novel_item['status']}")
        self.logger.info(f"  Genres: {self.novel_item['genres']}")

    def extract_chapter_list(self, response) -> list:
        self.logger.info("Starting chapter list extraction...")
        chapters = []

        novel_id = self.series_id
        limit = 30
        last_order = 0
        batch_count = 0

        session = requests.Session()
        session.headers.update(self._pixiv_headers())

        while True:
            batch_count += 1
            api_url = (
                f"https://www.pixiv.net/ajax/novel/series_content/"
                f"{novel_id}?limit={limit}&last_order={last_order}&order_by=asc"
            )

            self.logger.info(f"Fetching chapter batch {batch_count} (starting from chapter {last_order + 1})...")
            self.logger.info(f"API URL: {api_url}")

            try:
                r = session.get(api_url, timeout=15)
                r.raise_for_status()
            except Exception as e:
                self.logger.error(f"Failed to fetch chapter batch {batch_count}: {e}")
                raise

            try:
                data = PixivSeriesContentResponse.model_validate(r.json())
            except Exception as e:
                self.logger.error(f"Failed to parse chapter batch response: {e}")
                raise

            self.logger.info("Batch response data:")
            self.logger.info(r.json())
            self.logger.info(data)
            self.logger.info(data.body)
            self.logger.info(data.body.thumbnails)
            self.logger.info(data.body.thumbnails.novel)

            novels = data.body.thumbnails.novel

            # STOP condition
            if not novels:
                self.logger.info(f"No more chapters found. Completed after {batch_count} batches.")
                break

            self.logger.info(f"Found {len(novels)} chapters in batch {batch_count}")

            for idx, novel in enumerate(novels):
                chapter_number = last_order + idx + 1
                chapters.append({
                    "number": chapter_number,
                    "title": novel.title,
                    # "url": f"https://www.pixiv.net/novel/show.php?id={novel.id}",
                    "url": f"https://www.pixiv.net/ajax/novel/{novel.id}",
                })
                self.logger.debug(f"  Chapter {chapter_number}: {novel.title}")

            last_order += limit

        self.logger.info(f"✓ Chapter list extraction complete: {len(chapters)} total chapters found")
        return chapters

    def parse_chapter(self, response):
        """Parse chapter content from example.com."""
        chapter_number = response.meta['chapter_number']
        chapter_title = response.meta.get('chapter_title', 'Unknown')

        self.logger.info(f"Parsing chapter {chapter_number}: {chapter_title}")

        try:
            data = PixivNovelResponse.model_validate(response.json())
        except Exception as e:
            self.logger.error(f"Failed to parse chapter {chapter_number} response: {e}")
            return

        body = data.body

        content = body.content.strip()
        if not content:
            self.logger.warning(f"⚠ No content found for chapter {chapter_number}")
            return

        word_count = body.wordCount or len(content.split())
        self.logger.info(f"  Chapter {chapter_number} content length: {len(content)} chars, ~{word_count} words")

        tags = [t.tag for t in body.tags.tags]

        source_url = None
        match = re.search(r'/novel/(\d+)', response.url)
        if match:
            novel_id = match.group(1)
            source_url = f"https://www.pixiv.net/novel/show.php?id={novel_id}"

        # Create chapter item
        chapter_item = ChapterItem()
        chapter_item['chapter_number'] = chapter_number
        chapter_item['chapter_title'] = data.body.title
        chapter_item['source_url'] = source_url
        chapter_item['content'] = content
        chapter_item['genres'] = tags

        # Add to novel's chapter list
        self.novel_item['chapters'].append(dict(chapter_item))

        total_chapters = len(self.novel_item['chapters'])
        self.logger.info(f"✓ Chapter {chapter_number} parsed successfully ({total_chapters} chapters collected so far)")

    def _pixiv_headers(self) -> dict:
        return {
            "Accept": "application/json",
            "Referer": self.source_url,
        }
