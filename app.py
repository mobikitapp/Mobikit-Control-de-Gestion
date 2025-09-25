import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
migrate = Migrate()

def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # File upload configuration
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    app.config["ALLOWED_MIME_TYPES"] = os.environ.get("ALLOWED_MIME", "application/pdf,image/jpeg,image/png").split(",")
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # Import models to ensure they are registered
        import models  # noqa: F401
        
        # Create tables only if they don't exist
        try:
            db.create_all()
            logging.info("Database tables verified/created")
        except Exception as e:
            logging.warning(f"Database table creation warning: {str(e)}")
            # Continue anyway, tables might already exist

    return app

# Create the app instance
app = create_app()
