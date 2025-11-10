"""
BudtBoy Application Factory
"""
import os
from flask import Flask
from flask_mail import Mail
from config import config
from app.models import Database
from app.utils import CacheManager


# Initialize extensions
mail = Mail()


def create_app(config_name='development'):
    """
    Application factory pattern

    Args:
        config_name: Configuration name (development, production, testing)

    Returns:
        Flask application instance
    """
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Ensure upload folders exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ATTACHED_ASSETS_FOLDER'], exist_ok=True)

    # Initialize database
    db = Database(app.config['DATABASE_PATH'])
    db.init_db()

    # Run migrations
    db.migrate_add_referrer_approval()
    db.migrate_add_activity_criteria()
    db.migrate_fix_activity_status()

    app.db = db

    # Initialize cache
    cache = CacheManager()
    app.cache = cache

    # Initialize Flask-Mail
    mail.init_app(app)

    # Configure logging (always enabled)
    import logging
    from logging.handlers import RotatingFileHandler

    # Create logs directory
    if not os.path.exists('logs'):
        os.mkdir('logs')

    # File handler for all environments
    file_handler = RotatingFileHandler(
        'logs/budtboy.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    # Set logging level based on environment
    if app.config['DEBUG']:
        file_handler.setLevel(logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
        app.logger.setLevel(logging.INFO)

    app.logger.addHandler(file_handler)

    # Console handler for development
    if app.config['DEBUG']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s: %(message)s'
        ))
        console_handler.setLevel(logging.INFO)
        app.logger.addHandler(console_handler)

    app.logger.info(f'BudtBoy startup - Environment: {config_name}')

    # Register blueprints
    from app.routes import auth_bp, main_bp, admin_bp, api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # Security headers middleware
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        # Prevent clickjacking attacks
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # Enable XSS protection
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # Content Security Policy (adjust as needed)
        if not app.config['DEBUG']:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self'"
            )

        # Strict Transport Security (HTTPS only - enable in production)
        if not app.config['DEBUG']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions Policy (formerly Feature-Policy)
        response.headers['Permissions-Policy'] = (
            'geolocation=(), '
            'microphone=(), '
            'camera=()'
        )

        return response

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f'404 error: {error}')
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'500 error: {error}')
        return {'error': 'Internal server error'}, 500

    return app
