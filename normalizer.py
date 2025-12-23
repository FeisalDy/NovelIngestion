"""Content normalization and cleaning utilities."""
import re
from bs4 import BeautifulSoup
import bleach
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ContentCleaner:
    """
    Clean and normalize HTML content from scraped chapters.
    
    Removes ads, scripts, navigation, and other junk.
    Produces clean, reader-friendly HTML.
    """
    
    # Allowed HTML tags for chapter content
    ALLOWED_TAGS = [
        'p', 'br', 'em', 'strong', 'b', 'i', 'u',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'ol', 'ul', 'li',
        'hr', 'span', 'div'
    ]
    
    # Allowed attributes
    ALLOWED_ATTRIBUTES = {
        '*': ['class'],
    }
    
    # Common ad/navigation class patterns
    JUNK_PATTERNS = [
        r'ad[s]?[-_]',
        r'advertisement',
        r'banner',
        r'sidebar',
        r'navigation',
        r'nav[-_]',
        r'menu',
        r'footer',
        r'header',
        r'social',
        r'share',
        r'comment',
        r'popup',
        r'modal',
        r'related',
    ]
    
    def __init__(self):
        self.junk_pattern = re.compile('|'.join(self.JUNK_PATTERNS), re.IGNORECASE)
    
    def clean_html(self, html: str) -> str:
        """
        Clean HTML content.
        
        Args:
            html: Raw HTML string
            
        Returns:
            Cleaned HTML string
        """
        if not html:
            return ""
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove script and style tags
        for tag in soup(['script', 'style', 'iframe', 'noscript']):
            tag.decompose()
        
        # Remove elements with junk classes/ids
        for element in soup.find_all(class_=True):
            classes = ' '.join(element.get('class', []))
            if self.junk_pattern.search(classes):
                element.decompose()
        
        for element in soup.find_all(id=True):
            element_id = element.get('id', '')
            if self.junk_pattern.search(element_id):
                element.decompose()
        
        # Get the content
        content_html = str(soup)
        
        # Bleach for final cleaning
        clean_html = bleach.clean(
            content_html,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            strip=True,
        )
        
        # Normalize whitespace
        clean_html = self._normalize_whitespace(clean_html)
        
        return clean_html
    
    def _normalize_whitespace(self, html: str) -> str:
        """Normalize paragraph spacing and whitespace."""
        # Remove excessive newlines
        html = re.sub(r'\n{3,}', '\n\n', html)
        
        # Remove excessive spaces
        html = re.sub(r' {2,}', ' ', html)
        
        # Clean up empty tags
        html = re.sub(r'<p>\s*</p>', '', html)
        html = re.sub(r'<div>\s*</div>', '', html)
        
        return html.strip()
    
    def extract_text(self, html: str) -> str:
        """
        Extract plain text from HTML.
        
        Args:
            html: HTML string
            
        Returns:
            Plain text
        """
        soup = BeautifulSoup(html, 'lxml')
        return soup.get_text(separator=' ', strip=True)
    
    def count_words(self, html: str) -> int:
        """
        Count words in HTML content.
        
        Args:
            html: HTML string
            
        Returns:
            Word count
        """
        text = self.extract_text(html)
        words = text.split()
        return len(words)


class SlugGenerator:
    """Generate URL-safe slugs from titles."""
    
    @staticmethod
    def generate_slug(text: str) -> str:
        """
        Generate a URL-safe slug from text.
        
        Args:
            text: Input text (e.g., novel title)
            
        Returns:
            Slugified text
        """
        from slugify import slugify
        return slugify(text, max_length=500)


class GenreNormalizer:
    """
    Normalize genre names from various sources.
    
    Maps raw genre strings to standardized genre names.
    """
    
    # Genre mapping for common variations
    GENRE_MAPPINGS = {
        # Fantasy variants
        'fantasy': 'fantasy',
        'high fantasy': 'high-fantasy',
        'urban fantasy': 'urban-fantasy',
        'dark fantasy': 'dark-fantasy',
        
        # Asian web novel genres
        'xianxia': 'xianxia',
        'xuanhuan': 'xuanhuan',
        'wuxia': 'wuxia',
        'cultivation': 'cultivation',
        
        # Common genres
        'action': 'action',
        'adventure': 'adventure',
        'romance': 'romance',
        'mystery': 'mystery',
        'horror': 'horror',
        'thriller': 'thriller',
        'sci-fi': 'science-fiction',
        'science fiction': 'science-fiction',
        'scifi': 'science-fiction',
        'drama': 'drama',
        'comedy': 'comedy',
        'slice of life': 'slice-of-life',
        'psychological': 'psychological',
        'supernatural': 'supernatural',
        'martial arts': 'martial-arts',
        'historical': 'historical',
        'tragedy': 'tragedy',
        'seinen': 'seinen',
        'shounen': 'shounen',
        'isekai': 'isekai',
        'litrpg': 'litrpg',
        'progression': 'progression',
        'system': 'system',
    }
    
    @classmethod
    def normalize_genre(cls, raw_genre: str) -> Optional[str]:
        """
        Normalize a single genre name.
        
        Args:
            raw_genre: Raw genre string from source
            
        Returns:
            Normalized genre slug or None if invalid
        """
        if not raw_genre:
            return None
        
        # Clean and lowercase
        clean = raw_genre.strip().lower()
        
        # Direct mapping
        if clean in cls.GENRE_MAPPINGS:
            return cls.GENRE_MAPPINGS[clean]
        
        # Generate slug as fallback
        slug = SlugGenerator.generate_slug(clean)
        
        # Validate (must be reasonable length)
        if slug and 2 <= len(slug) <= 50:
            return slug
        
        return None
    
    @classmethod
    def normalize_genres(cls, raw_genres: list[str]) -> list[str]:
        """
        Normalize a list of genre names.
        
        Args:
            raw_genres: List of raw genre strings
            
        Returns:
            List of normalized genre slugs (deduplicated)
        """
        if not raw_genres:
            return []
        
        normalized = set()
        
        for genre in raw_genres:
            slug = cls.normalize_genre(genre)
            if slug:
                normalized.add(slug)
        
        return sorted(list(normalized))
