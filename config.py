import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get("SESSION_SECRET")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # File upload settings
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    ALLOWED_MIME_TYPES = os.environ.get("ALLOWED_MIME", "application/pdf,image/jpeg,image/png").split(",")
    
    # Storage settings
    STORAGE_BASE_URL = os.environ.get("STORAGE_BASE_URL", "")
    STORAGE_BUCKET = os.environ.get("STORAGE_BUCKET", "")
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=31)
    
    # Timezone
    TIMEZONE = "America/Santiago"

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
