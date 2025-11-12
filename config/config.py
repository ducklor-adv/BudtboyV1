import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-please-change'

    # Database
    DATABASE_TYPE = os.environ.get('DATABASE_TYPE', 'sqlite')  # 'sqlite' or 'postgresql'
    DATABASE_PATH = os.environ.get('DATABASE_PATH', 'budtboy_local.db')  # For SQLite
    DATABASE_URL = os.environ.get('DATABASE_URL')  # For PostgreSQL

    # File Upload
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    ATTACHED_ASSETS_FOLDER = 'attached_assets'
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = None  # Allow cross-site for OAuth callbacks

    # Email
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))
    MAIL_USE_SSL = False

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

    # Admin
    ADMIN_MASTER_PASSWORD = os.environ.get('ADMIN_MASTER_PASSWORD', 'Admin123!@#')

    # Cache TTL (seconds)
    CACHE_TTL = 900  # 15 minutes
    SHORT_CACHE_TTL = 180  # 3 minutes
    PROFILE_CACHE_TTL = 1800  # 30 minutes
    ACTIVITY_CACHE_TTL = 600  # 10 minutes

    # Application
    FALLBACK_AUTH_ENABLED = os.environ.get('FALLBACK_AUTH_ENABLED', 'True').lower() == 'true'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # Require HTTPS
    FALLBACK_AUTH_ENABLED = False
    DATABASE_TYPE = 'postgresql'  # Use PostgreSQL in production


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_PATH = ':memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
