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

            # Auto-change proyecto estado to EN_DESARROLLO
            from services.proyectos_service import ProyectosService
            proyectos_service = ProyectosService()
            proyectos_service.cambiar_estado_por_contrato_creado(contrato.proyecto_id)

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
        contrato = self.repo.get_by_id(contrato_id)
        if contrato:
            self._enrich_contrato_with_next_milestone(contrato)
        return contrato

    def get_contratos_by_cliente(self, cliente_id: int) -> List[Contrato]:
        """Get all contratos for a cliente"""
        return self.repo.get_by_cliente_id(cliente_id)

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
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                return False

            self.repo.delete(contrato)
            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting contrato {contrato_id}: {str(e)}")
            raise

    def get_contratos_by_proyecto(self, proyecto_id: int) -> List[Contrato]:
        """Get all contratos for a proyecto"""
        try:
            contratos = self.repo.get_by_proyecto(proyecto_id)

            # Enrich each contract with additional info
            for contrato in contratos:
                self._enrich_contrato_with_ofs_info(contrato)

            return contratos
        except Exception as e:
            logger.error(f"Error getting contratos for proyecto {proyecto_id}: {str(e)}")
            raise

    def get_all_contratos(self) -> List[Contrato]:
        """Get all contratos with basic filters"""
        try:
            from schemas.contratos import ContratoSearchFilters
            # Use search with empty filters to get all contratos
            filters = ContratoSearchFilters(page=1, per_page=1000)  # Large per_page to get all
            contratos, _ = self.repo.search(filters)
            return contratos
        except Exception as e:
            logger.error(f"Error getting all contratos: {str(e)}")
            raise

    def get_contratos_grouped_by_client(self, filters: ContratoSearchFilters) -> tuple[List[Dict], int]:
        """
        Get contratos grouped by client and project

        Returns:
            Tuple of (grouped_data, total_count)
        """
        try:
            contratos, total_count = self.repo.search(filters)

            # Enrich contracts with next delivery milestone info
            for contrato in contratos:
                self._enrich_contrato_with_next_milestone(contrato)

            # Group contracts by client and project
            grouped_data = {}

            for contrato in contratos:
                cliente_id = contrato.proyecto.cliente.id
                proyecto_id = contrato.proyecto.id

                # Initialize client data if not exists
                if cliente_id not in grouped_data:
                    grouped_data[cliente_id] = {
                        'cliente': contrato.proyecto.cliente,
                        'proyectos': {},
                        'total_contratos': 0
                    }

                # Initialize project data if not exists
                if proyecto_id not in grouped_data[cliente_id]['proyectos']:
                    grouped_data[cliente_id]['proyectos'][proyecto_id] = {
                        'proyecto': contrato.proyecto,
                        'contratos': []
                    }

                # Add contract to project
                grouped_data[cliente_id]['proyectos'][proyecto_id]['contratos'].append(contrato)
                grouped_data[cliente_id]['total_contratos'] += 1

            # Convert to list format for template
            result = []
            for cliente_data in grouped_data.values():
                proyectos_list = list(cliente_data['proyectos'].values())
                # Sort projects by name
                proyectos_list.sort(key=lambda p: p['proyecto'].nombre)

                result.append({
                    'cliente': cliente_data['cliente'],
                    'proyectos': proyectos_list,
                    'total_contratos': cliente_data['total_contratos']
                })

            # Sort clients by name
            result.sort(key=lambda c: c['cliente'].nombre)

            return result, total_count

        except Exception as e:
            logger.error(f"Error grouping contratos by client: {str(e)}")
            raise

    def _enrich_contrato_with_next_milestone(self, contrato):
        """
        Enrich contract with next delivery milestone information and OFs data
        """
        try:
            from datetime import date
            from models import EstadoHitoEntrega

            # Initialize default values
            contrato.fecha_proxima_entrega = None
            contrato.proximo_hito = None
            contrato.dias_restantes_proxima_entrega = None

            # Enrich with OFs information
            self._enrich_contrato_with_ofs_info(contrato)

            if contrato.plan_entrega and contrato.plan_entrega.hitos:
                # Get pending milestones sorted by date and order
                hitos_pendientes = [
                    hito for hito in contrato.plan_entrega.hitos 
                    if hito.estado == EstadoHitoEntrega.PENDIENTE
                ]

                if hitos_pendientes:
                    # Sort by date first, then by order
                    hitos_pendientes.sort(key=lambda x: (x.fecha_programada, x.orden))
                    proximo_hito = hitos_pendientes[0]

                    contrato.fecha_proxima_entrega = proximo_hito.fecha_programada
                    contrato.proximo_hito = proximo_hito

                    # Calculate days remaining
                    today = date.today()
                    days_diff = (proximo_hito.fecha_programada - today).days
                    contrato.dias_restantes_proxima_entrega = days_diff
                else:
                    # No pending milestones, check if there are completed ones
                    hitos_completados = [
                        hito for hito in contrato.plan_entrega.hitos 
                        if hito.estado == EstadoHitoEntrega.COMPLETADO
                    ]

                    if hitos_completados:
                        # All milestones completed, use the last one
                        hitos_completados.sort(key=lambda x: (x.fecha_programada, x.orden))
                        ultimo_hito = hitos_completados[-1]
                        contrato.fecha_proxima_entrega = ultimo_hito.fecha_programada
                        contrato.proximo_hito = ultimo_hito
                        contrato.dias_restantes_proxima_entrega = 0  # Already completed

            # Fallback to contract delivery date if no plan exists
            elif contrato.fecha_entrega_comprometida:
                contrato.fecha_proxima_entrega = contrato.fecha_entrega_comprometida
                contrato.proximo_hito = None

                # Calculate days remaining
                today = date.today()
                days_diff = (contrato.fecha_entrega_comprometida - today).days
                contrato.dias_restantes_proxima_entrega = days_diff

        except Exception as e:
            logger.warning(f"Error enriching contrato {contrato.id} with milestone info: {str(e)}")
            # Set default values on error
            contrato.fecha_proxima_entrega = contrato.fecha_entrega_comprometida
            contrato.proximo_hito = None
            contrato.dias_restantes_proxima_entrega = None

    def _enrich_contrato_with_ofs_info(self, contrato):
        """
        Enrich contract with manufacturing orders information
        """
        try:
            from models import OrdenFabricacion

            # Get all manufacturing orders for this contract
            ofs = (db.session.query(OrdenFabricacion)
                   .filter_by(contrato_id=contrato.id)
                   .order_by(OrdenFabricacion.fecha_planificada.asc())
                   .all())

            # Initialize OFs data
            contrato.ordenes_fabricacion_count = len(ofs)
            contrato.ordenes_fabricacion_list = []

            if ofs:
                for of in ofs:
                    # Get current area and status
                    area_actual = None
                    estado_actual = None

                    if of.area_progreso_actual:
                        area_actual = of.area_progreso_actual.area.nombre if of.area_progreso_actual.area else None
                        estado_actual = of.area_progreso_actual.estado.nombre if of.area_progreso_actual.estado else None

                    of_info = {
                        'id': of.id,
                        'codigo': of.codigo,
                        'descripcion': of.descripcion,
                        'fecha_entrega_fabrica': of.fecha_entrega_fabrica,
                        'area_actual': area_actual or 'Sin asignar',
                        'estado_actual': estado_actual or 'Sin estado',
                        'responsable': of.responsable_user.nombre_completo if of.responsable_user else 'Sin asignar'
                    }

                    contrato.ordenes_fabricacion_list.append(of_info)
            else:
                contrato.ordenes_fabricacion_count = 0
                contrato.ordenes_fabricacion_list = []

        except Exception as e:
            logger.warning(f"Error enriching contrato {contrato.id} with OFs info: {str(e)}")
            # Set default values on error
            contrato.ordenes_fabricacion_count = 0
            contrato.ordenes_fabricacion_list = []