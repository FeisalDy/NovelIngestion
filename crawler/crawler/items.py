"""Scrapy items for novel data extraction."""
import scrapy
from typing import List, Optional


class ChapterItem(scrapy.Item):
    """Item representing a single chapter."""
    chapter_number = scrapy.Field()
    chapter_title = scrapy.Field()
    chapter_url = scrapy.Field()
    content = scrapy.Field()  # Raw HTML content


class NovelItem(scrapy.Item):
    """Item representing a novel with all its data."""
    title = scrapy.Field()
    synopsis = scrapy.Field()
    source_url = scrapy.Field()
    status = scrapy.Field()  # 'ongoing' or 'completed'
    genres = scrapy.Field()  # List of genre strings
    chapters = scrapy.Field()  # List of ChapterItem dictionaries
    ingestion_job_id = scrapy.Field()  # Track which job this belongs to
