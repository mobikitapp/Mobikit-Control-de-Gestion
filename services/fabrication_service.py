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