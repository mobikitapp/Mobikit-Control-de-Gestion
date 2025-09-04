def smart_advance_orden(self, of_id: int, created_by: str, notas: str = None) -> tuple[bool, str]:
    """
    Avanza una orden de fabricación al siguiente estado o área, asignando automáticamente el usuario actual como responsable.
    """
    try:
        # Obtener el estado actual de la orden de fabricación
        current_state = self.get_orden_fabricacion_state(of_id)
        if not current_state:
            return False, "No se pudo obtener el estado actual de la orden de fabricación."

        # Obtener el siguiente estado o área
        next_state_or_area = self.get_next_state_or_area(current_state.id)
        if not next_state_or_area:
            return False, "No se pudo determinar el siguiente estado o área."

        # Si el siguiente paso es una nueva área, se avanza en el servicio de áreas
        if hasattr(next_state_or_area, 'area_id'):
            self.areas_service.advance_to_next_area(
                of_id,
                created_by,
                responsable_id=created_by,
                notas=notas
            )
        else:
            # Si es un cambio de estado dentro de la misma área
            self.areas_service.change_estado_in_area(
                of_id,
                next_state_or_area.id,
                responsable_id=created_by,
                notas=notas
            )

        return True, "Avance de orden de fabricación realizado con éxito."

    except Exception as e:
        # Loguear el error para su posterior análisis
        # self.log.error(f"Error al avanzar la orden de fabricación {of_id}: {e}")
        return False, f"Error al avanzar la orden de fabricación: {str(e)}"

def get_next_action_description(self, orden_id: int) -> str:
        """
        Get description of the next action for an order based on current area/state
        """
        try:
            orden = self.fabricacion_repo.get_by_id(orden_id)
            if not orden:
                return "Avanzar"

            current_progress = orden.area_progreso_actual
            if not current_progress:
                return "Iniciar en Producción"

            area_tipo = current_progress.area.tipo.value
            estado_codigo = current_progress.estado.codigo

            # Define action descriptions based on area and state
            action_map = {
                'pendientes_fabricacion': {
                    'pendiente_aprobacion_diseño': 'Aprobar Diseño',
                    'aprobado': 'Enviar a Fábrica'
                },
                'fabrica': {
                    'enviado_a_fabricacion': 'Iniciar Seccionado',
                    'seccionando': 'Iniciar Enchapado',
                    'enchapando': 'Iniciar Mecanizado',
                    'mecanizando': 'Completar Fabricación',
                    'fabricacion_completa': 'Enviar a Embalaje'
                },
                'embalaje': {
                    'pendiente_de_embalar': 'Iniciar Embalaje',
                    'embalando': 'Completar Embalaje',
                    'embalaje_listo': 'Enviar a Bodega'
                },
                'bodega': {
                    'listo_para_despacho': 'Programar Despacho',
                    'programado_para_despacho': 'Despachar'
                },
                'despacho': {
                    'despachado': 'Archivar'
                }
            }

            area_actions = action_map.get(area_tipo, {})
            return area_actions.get(estado_codigo, 'Avanzar')

        except Exception as e:
            logger.error(f"Error getting next action for order {orden_id}: {str(e)}")
            return "Avanzar"

def get_archived_orders(self, page: int = 1, per_page: int = 20, 
                           cliente_id: int = None, proyecto_id: int = None, 
                           codigo: str = None) -> tuple[List, int]:
        """
        Get archived orders with pagination and filters
        """
        try:
            from models import OrdenFabricacion, OrdenAreaProgreso, Proyecto, Cliente
            from sqlalchemy import and_, desc
            from sqlalchemy.orm import joinedload

            # Base query for archived orders
            query = (db.session.query(OrdenFabricacion)
                    .join(OrdenAreaProgreso, and_(
                        OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                        OrdenAreaProgreso.archivado == True
                    ))
                    .options(
                        joinedload(OrdenFabricacion.proyecto).joinedload(Proyecto.cliente),
                        joinedload(OrdenFabricacion.contrato),
                        joinedload(OrdenFabricacion.area_progresos)
                    ))

            # Apply filters
            conditions = []

            if cliente_id:
                query = query.join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                conditions.append(Proyecto.cliente_id == cliente_id)

            if proyecto_id:
                conditions.append(OrdenFabricacion.proyecto_id == proyecto_id)

            if codigo:
                conditions.append(OrdenFabricacion.codigo.ilike(f"%{codigo}%"))

            if conditions:
                query = query.filter(and_(*conditions))

            # Get total count
            total_count = query.count()

            # Apply pagination and ordering
            orders = (query.order_by(desc(OrdenFabricacion.updated_at))
                     .offset((page - 1) * per_page)
                     .limit(per_page)
                     .all())

            return orders, total_count

        except Exception as e:
            logger.error(f"Error getting archived orders: {str(e)}")
            raise