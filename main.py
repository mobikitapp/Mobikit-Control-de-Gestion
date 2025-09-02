import os
import logging

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from app import app
    import routes  # noqa: F401
    logger.info("Application imported successfully")
except ImportError as e:
    logger.error(f"Import error: {str(e)}")
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
