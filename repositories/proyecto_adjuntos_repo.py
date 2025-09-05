
from typing import List, Optional
from app import db
from models import ProyectoAdjunto
import logging

logger = logging.getLogger(__name__)

class ProyectoAdjuntosRepository:
    """Repository for ProyectoAdjunto operations"""

    def create(self, adjunto_data: dict, created_by: str) -> ProyectoAdjunto:
        """Create a new proyecto adjunto"""
        try:
            adjunto = ProyectoAdjunto(**adjunto_data)
            adjunto.created_by = created_by
            db.session.add(adjunto)
            db.session.flush()
            return adjunto
        except Exception as e:
            logger.error(f"Error creating proyecto adjunto: {str(e)}")
            raise

    def get_by_id(self, adjunto_id: int) -> Optional[ProyectoAdjunto]:
        """Get proyecto adjunto by ID"""
        try:
            return ProyectoAdjunto.query.get(adjunto_id)
        except Exception as e:
            logger.error(f"Error getting proyecto adjunto {adjunto_id}: {str(e)}")
            return None

    def get_by_proyecto_id(self, proyecto_id: int) -> List[ProyectoAdjunto]:
        """Get all adjuntos for a proyecto"""
        try:
            return (ProyectoAdjunto.query
                   .filter_by(proyecto_id=proyecto_id)
                   .order_by(ProyectoAdjunto.created_at.desc())
                   .all())
        except Exception as e:
            logger.error(f"Error getting adjuntos for proyecto {proyecto_id}: {str(e)}")
            return []

    def delete(self, adjunto: ProyectoAdjunto) -> bool:
        """Delete proyecto adjunto"""
        try:
            db.session.delete(adjunto)
            db.session.flush()
            return True
        except Exception as e:
            logger.error(f"Error deleting proyecto adjunto {adjunto.id}: {str(e)}")
            return False
