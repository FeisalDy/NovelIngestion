"""Database models for novel ingestion system."""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, 
    ForeignKey, Index, Table, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class IngestionStatus(str, enum.Enum):
    """Ingestion job states."""
    QUEUED = "queued"
    CRAWLING = "crawling"
    PARSING = "parsing"
    SAVING = "saving"
    DONE = "done"
    ERROR = "error"


class NovelStatus(str, enum.Enum):
    """Novel publication status."""
    ONGOING = "ongoing"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


# Many-to-many association table
novel_genres = Table(
    'novel_genres',
    Base.metadata,
    Column('novel_id', Integer, ForeignKey('novels.id', ondelete='CASCADE'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_novel_genres_novel_id', 'novel_id'),
    Index('ix_novel_genres_genre_id', 'genre_id'),
)


class Novel(Base):
    """Novel model."""
    __tablename__ = 'novels'
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(500), nullable=False, unique=True, index=True)
    synopsis = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=False, unique=True)
    status = Column(Enum(NovelStatus), default=NovelStatus.UNKNOWN, nullable=False)
    word_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    genres = relationship("Genre", secondary=novel_genres, back_populates="novels")
    
    def __repr__(self):
        return f"<Novel(id={self.id}, title='{self.title}', slug='{self.slug}')>"


class Chapter(Base):
    """Chapter model."""
    __tablename__ = 'chapters'
    
    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey('novels.id', ondelete='CASCADE'), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    novel = relationship("Novel", back_populates="chapters")
    
    # Unique constraint on novel_id + chapter_number
    __table_args__ = (
        Index('ix_chapters_novel_chapter', 'novel_id', 'chapter_number', unique=True),
    )
    
    def __repr__(self):
        return f"<Chapter(id={self.id}, novel_id={self.novel_id}, number={self.chapter_number})>"


class Genre(Base):
    """Genre model."""
    __tablename__ = 'genres'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    # Relationships
    novels = relationship("Novel", secondary=novel_genres, back_populates="genres")
    
    def __repr__(self):
        return f"<Genre(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class IngestionJob(Base):
    """Ingestion job tracking."""
    __tablename__ = 'ingestion_jobs'
    
    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String(1000), nullable=False, index=True)
    status = Column(Enum(IngestionStatus), default=IngestionStatus.QUEUED, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<IngestionJob(id={self.id}, status='{self.status}', url='{self.source_url}')>"
