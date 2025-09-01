from typing import List, Optional, Dict, Any
from werkzeug.datastructures import FileStorage
from app import db
from repositories.contratos_repo import ContratosRepository, ContratoAdjuntosRepository
from repositories.proyectos_repo import ProyectosRepository
from services.audit_service import AuditService, serialize_model
from services.storage_service import StorageService
from schemas.contratos import ContratoSearchFilters
from models import Contrato, ContratoAdjunto, EstadoContrato, TipoAdjunto
import logging

logger = logging.getLogger(__name__)

class ContratosService:
    """Service layer for Contrato operations"""

    def __init__(self):
        self.repo = ContratosRepository()
        self.adjuntos_repo = ContratoAdjuntosRepository()
        self.proyectos_repo = ProyectosRepository()
        self.storage_service = StorageService()

    def create_contrato(self, contrato_data: Dict[str, Any], created_by: str) -> Contrato:
        """
        Create a new contrato with validation and audit logging

        Args:
            contrato_data: Contrato data dictionary
            created_by: User ID who is creating the contrato

        Returns:
            Created Contrato instance
        """
        try:
            # Validate proyecto exists
            proyecto = self.proyectos_repo.get_by_id(contrato_data['proyecto_id'])
            if not proyecto:
                raise ValueError(f"Proyecto {contrato_data['proyecto_id']} no encontrado")

            # Check if numero_oc already exists
            if self.repo.exists_numero_oc(contrato_data['numero_oc']):
                raise ValueError(f"Ya existe un contrato con número OC {contrato_data['numero_oc']}")

            # Extract categoria_ids before creating contrato
            categoria_ids = contrato_data.pop('categoria_ids', [])

            # Create contrato
            contrato = self.repo.create(contrato_data, created_by)

            # Handle categorías if provided
            if categoria_ids:
                from models import CategoriaMuebleModel
                categorias = CategoriaMuebleModel.query.filter(CategoriaMuebleModel.id.in_(categoria_ids)).all()
                contrato.categorias_mueble = categorias

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'contratos', 
                contrato.id, 
                'CREATE', 
                datos_nuevos=serialize_model(contrato)
            )

            logger.info(f"Contrato creado: {contrato.id} - {contrato.numero_oc}")
            return contrato

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando contrato: {str(e)}")
            raise

    def create_contrato_with_files(self, contrato_data: Dict[str, Any], 
                                   files: List[FileStorage], created_by: str) -> Contrato:
        """
        Create contrato with file uploads in a single transaction

        Args:
            contrato_data: Contrato data dictionary
            files: List of uploaded files
            created_by: User ID who is creating the contrato

        Returns:
            Created Contrato instance
        """
        try:
            # Create contrato
            contrato = self.create_contrato(contrato_data, created_by)

            # Upload files
            for file in files:
                if file and file.filename:
                    self.add_contract_attachment(contrato.id, file, 'contrato', created_by)

            logger.info(f"Contrato creado con {len(files)} archivos: {contrato.numero_oc}")
            return contrato

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando contrato con archivos: {str(e)}")
            raise

    def get_contrato_by_id(self, contrato_id: int) -> Optional[Contrato]:
        """Get contrato by ID with related data"""
        return self.repo.get_by_id(contrato_id)

    def update_contrato(self, contrato_id: int, update_data: Dict[str, Any]) -> Contrato:
        """
        Update contrato with validation and audit logging

        Args:
            contrato_id: Contrato ID to update
            update_data: Dictionary with fields to update

        Returns:
            Updated Contrato instance
        """
        try:
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(contrato)

            # Validate proyecto if updating proyecto_id
            if 'proyecto_id' in update_data and update_data['proyecto_id'] != contrato.proyecto_id:
                proyecto = self.proyectos_repo.get_by_id(update_data['proyecto_id'])
                if not proyecto:
                    raise ValueError(f"Proyecto {update_data['proyecto_id']} no encontrado")

            # Check numero_oc uniqueness if updating numero_oc
            if 'numero_oc' in update_data and update_data['numero_oc'] != contrato.numero_oc:
                if self.repo.exists_numero_oc(update_data['numero_oc'], exclude_id=contrato_id):
                    raise ValueError(f"Ya existe un contrato con número OC {update_data['numero_oc']}")

            # Extract categoria_ids before updating contrato
            categoria_ids = update_data.pop('categoria_ids', None)

            # Update contrato
            contrato_actualizado = self.repo.update(contrato, update_data)

            # Handle categorías if provided
            if categoria_ids is not None:
                from models import CategoriaMuebleModel
                if categoria_ids:
                    categorias = CategoriaMuebleModel.query.filter(CategoriaMuebleModel.id.in_(categoria_ids)).all()
                    contrato_actualizado.categorias_mueble = categorias
                else:
                    contrato_actualizado.categorias_mueble = []

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'contratos', 
                contrato_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(contrato_actualizado)
            )

            logger.info(f"Contrato actualizado: {contrato_id} - {contrato_actualizado.numero_oc}")
            return contrato_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando contrato {contrato_id}: {str(e)}")
            raise

    def change_contract_status(self, contrato_id: int, new_status: str) -> bool:
        """
        Change contract status with business rules validation

        Args:
            contrato_id: Contrato ID
            new_status: New status value

        Returns:
            True if status change was successful
        """
        try:
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")

            new_status_enum = EstadoContrato(new_status)

            # Validate status transition
            can_change, error_msg = self.repo.can_change_status(contrato, new_status_enum)
            if not can_change:
                raise ValueError(error_msg)

            # Store original data for audit
            datos_anteriores = serialize_model(contrato)

            # Update status
            contrato_actualizado = self.repo.update(contrato, {'estado': new_status_enum})

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'contratos', 
                contrato_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(contrato_actualizado)
            )

            logger.info(f"Estado de contrato cambiado: {contrato_id} -> {new_status}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cambiando estado de contrato {contrato_id}: {str(e)}")
            raise

    def add_contract_attachment(self, contrato_id: int, file: FileStorage, 
                               tipo: str, created_by: str) -> ContratoAdjunto:
        """
        Add attachment to contract

        Args:
            contrato_id: Contrato ID
            file: Uploaded file
            tipo: Type of attachment
            created_by: User ID who is uploading

        Returns:
            Created ContratoAdjunto instance
        """
        try:
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")

            # Upload file
            file_metadata = self.storage_service.upload_file(
                file, 'contratos', contrato_id, 'docs', tipo
            )

            # Create adjunto record
            adjunto_data = {
                'contrato_id': contrato_id,
                'storage_key': file_metadata['storage_key'],
                'filename': file_metadata['filename'],
                'mime_type': file_metadata['mime_type'],
                'size_bytes': file_metadata['size_bytes'],
                'tipo': TipoAdjunto(tipo)
            }

            adjunto = self.adjuntos_repo.create(adjunto_data, created_by)

            # Commit transaction
            db.session.commit()

            logger.info(f"Adjunto agregado al contrato {contrato_id}: {file.filename}")
            return adjunto

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error agregando adjunto al contrato {contrato_id}: {str(e)}")
            raise

    def delete_contract_attachment(self, adjunto_id: int) -> int:
        """
        Delete contract attachment

        Args:
            adjunto_id: Adjunto ID to delete

        Returns:
            Contrato ID of the deleted attachment
        """
        try:
            adjunto = self.adjuntos_repo.get_by_id(adjunto_id)
            if not adjunto:
                raise ValueError(f"Adjunto {adjunto_id} no encontrado")

            contrato_id = adjunto.contrato_id

            # Delete file from storage
            self.storage_service.delete_file(adjunto.storage_key, 'contratos', contrato_id)

            # Delete adjunto record
            self.adjuntos_repo.delete(adjunto)

            # Commit transaction
            db.session.commit()

            logger.info(f"Adjunto eliminado del contrato {contrato_id}: {adjunto.filename}")
            return contrato_id

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando adjunto {adjunto_id}: {str(e)}")
            raise

    def search_contratos(self, filters: ContratoSearchFilters) -> tuple[List[Contrato], int]:
        """
        Search contratos with filters and pagination

        Args:
            filters: Search filters

        Returns:
            Tuple of (contratos_list, total_count)
        """
        try:
            return self.repo.search(filters)
        except Exception as e:
            logger.error(f"Error buscando contratos: {str(e)}")
            raise

    def delete_contrato(self, contrato_id: int) -> bool:
        """Delete a contrato"""
        try:
            contrato = self.contratos_repo.get_by_id(contrato_id)
            if not contrato:
                return False

            self.contratos_repo.delete(contrato)
            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting contrato {contrato_id}: {str(e)}")
            raise

    def get_contratos_by_proyecto(self, proyecto_id: int):
        """Get all contratos for a specific proyecto"""
        try:
            return self.contratos_repo.get_by_proyecto(proyecto_id)
        except Exception as e:
            logger.error(f"Error getting contratos for proyecto {proyecto_id}: {str(e)}")
            raise