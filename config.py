"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/novel_ingestion"
    database_url_sync: str = "postgresql://user:password@localhost:5432/novel_ingestion"
    
    # Redis
    redis_url: Optional[str] = "redis://localhost:6379/0"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True
    
    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100
    
    # Scrapy
    scrapy_project_path: str = "./crawler"
    
    # Environment
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
