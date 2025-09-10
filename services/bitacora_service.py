from datetime import datetime
from typing import List, Optional
from sqlalchemy import desc
from app import db
from models import BitacoraProyecto, User
from schemas.bitacora import BitacoraProyectoCreate, BitacoraProyectoResponse, BitacoraProyectoFilters
import logging

logger = logging.getLogger(__name__)

class BitacoraService:
    """Servicio para gestión de bitácora de proyectos"""

    def create_comentario(self, data: BitacoraProyectoCreate, usuario_id: str) -> BitacoraProyecto:
        """Crear nuevo comentario en bitácora"""
        try:
            comentario = BitacoraProyecto(
                proyecto_id=data.proyecto_id,
                usuario_id=usuario_id,
                comentario=data.comentario,
                tipo=data.tipo
            )
            
            db.session.add(comentario)
            db.session.commit()
            
            logger.info(f"Comentario agregado a bitácora del proyecto {data.proyecto_id} por usuario {usuario_id}")
            return comentario
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating bitacora comment: {str(e)}")
            raise e

    def get_comentarios_proyecto(self, filters: BitacoraProyectoFilters) -> List[BitacoraProyectoResponse]:
        """Obtener comentarios de bitácora de un proyecto"""
        try:
            query = BitacoraProyecto.query.filter_by(proyecto_id=filters.proyecto_id)
            
            # Aplicar filtros opcionales
            if filters.tipo:
                query = query.filter_by(tipo=filters.tipo)
            
            if filters.usuario_id:
                query = query.filter_by(usuario_id=filters.usuario_id)
            
            # Ordenar por fecha descendente (más reciente primero)
            query = query.order_by(desc(BitacoraProyecto.fecha_comentario))
            
            # Limitar resultados
            comentarios = query.limit(filters.limit).all()
            
            # Construir respuesta con información del usuario
            comentarios_response = []
            for comentario in comentarios:
                usuario = User.query.get(comentario.usuario_id)
                comentario_data = BitacoraProyectoResponse(
                    id=comentario.id,
                    proyecto_id=comentario.proyecto_id,
                    usuario_id=comentario.usuario_id,
                    usuario_nombre=usuario.nombre_completo if usuario else "Usuario desconocido",
                    comentario=comentario.comentario,
                    tipo=comentario.tipo,
                    fecha_comentario=comentario.fecha_comentario
                )
                comentarios_response.append(comentario_data)
            
            return comentarios_response
            
        except Exception as e:
            logger.error(f"Error getting bitacora comments for project {filters.proyecto_id}: {str(e)}")
            raise e

    def get_comentario_by_id(self, comentario_id: int) -> Optional[BitacoraProyecto]:
        """Obtener comentario específico por ID"""
        return BitacoraProyecto.query.get(comentario_id)

    def delete_comentario(self, comentario_id: int, usuario_id: str) -> bool:
        """Eliminar comentario de bitácora (solo admin o autor)"""
        try:
            comentario = BitacoraProyecto.query.get(comentario_id)
            if not comentario:
                return False
            
            # Verificar permisos (solo admin o autor puede eliminar)
            usuario = User.query.get(usuario_id)
            if not usuario:
                return False
            
            if comentario.usuario_id != usuario_id and usuario.rol.value != 'admin':
                logger.warning(f"Usuario {usuario_id} intentó eliminar comentario {comentario_id} sin permisos")
                return False
            
            db.session.delete(comentario)
            db.session.commit()
            
            logger.info(f"Comentario {comentario_id} eliminado por usuario {usuario_id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting bitacora comment {comentario_id}: {str(e)}")
            return False

# Instancia del servicio
bitacora_service = BitacoraService()