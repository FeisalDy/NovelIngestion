"""Scrapy items for novel data extraction."""
import scrapy


class ChapterItem(scrapy.Item):
    """Item representing a single chapter."""
    chapter_number = scrapy.Field()
    chapter_title = scrapy.Field()
    source_url = scrapy.Field()
    content = scrapy.Field()  # Raw HTML content
    clean_content = scrapy.Field()  # optional, for pipeline
    word_count = scrapy.Field()  # optional, for pipeline
    genres = scrapy.Field()  # List of genre strings


class NovelItem(scrapy.Item):
    """Item representing a novel with all its data."""
    title = scrapy.Field()
    synopsis = scrapy.Field()
    source_url = scrapy.Field()
    status = scrapy.Field()  # 'ongoing' or 'completed'
    genres = scrapy.Field()  # List of genre strings
    chapters = scrapy.Field()  # List of ChapterItem dictionaries
    ingestion_job_id = scrapy.Field()  # Track which job this belongs to
    is_one_shot = scrapy.Field()  # Boolean flag for one-shots
