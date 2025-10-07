import os
import logging
from datetime import datetime

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from app import app, db
    
    # Add builtin functions to Jinja2 context
    app.jinja_env.globals['min'] = min
    app.jinja_env.globals['max'] = max

    # Add moment function to template globals
    @app.template_global('moment_global')
    def moment_global():
        try:
            return datetime.now()
        except Exception as e:
            logger.error(f"Error in moment_global: {e}")
            return datetime.now()
    
    # Add now function for datetime access in templates
    @app.template_global('now')
    def now():
        try:
            return datetime.now()
        except Exception as e:
            logger.error(f"Error in now function: {e}")
            return datetime.now()
    
    # Add timestamp function for cache busting
    @app.template_global('timestamp')
    def timestamp():
        try:
            return int(datetime.now().timestamp())
        except Exception as e:
            logger.error(f"Error in timestamp function: {e}")
            return int(datetime.now().timestamp())

    # Initialize database with better error handling
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}", exc_info=True)
        # Continue anyway - migrations might handle it

    # Add cache control headers
    @app.after_request
    def after_request(response):
        try:
            from flask import request
            # Prevent caching for HTML pages and API responses
            if response.mimetype == 'text/html' or '/api/' in request.path:
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            return response
        except Exception as e:
            logger.error(f"Error in after_request: {e}")
            return response

    # Import routes after app creation
    import routes  # noqa: F401

    logger.info("Application imported successfully")

except ImportError as e:
    logger.error(f"Import error: {str(e)}", exc_info=True)
    raise
except Exception as e:
    logger.error(f"Unexpected error during application startup: {str(e)}", exc_info=True)
    raise

if __name__ == "__main__":
    # More robust configuration for development
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.environ.get('DEBUG', 'True').lower() == 'true',
        threaded=True,
        use_reloader=False  # Disable reloader to prevent conflicts
    )