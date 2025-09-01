"""
Normalizador central de enums para garantizar consistencia en toda la aplicación
"""
from typing import Union, Any
from enum import Enum

class EnumNormalizer:
    """Clase centralizada para normalizar valores de enum"""
    
    @staticmethod
    def normalize_enum_value(value: Any, enum_class: type = None) -> str:
        """
        Normaliza cualquier valor a formato UPPERCASE estándar de BD
        
        Args:
            value: Valor a normalizar (puede ser enum, string, etc.)
            enum_class: Clase enum opcional para validación
            
        Returns:
            String en formato UPPERCASE compatible con BD
        """
        if value is None:
            return None
            
        # Si es instancia de enum, obtener su valor
        if hasattr(value, 'value'):
            normalized = str(value.value).upper()
        else:
            normalized = str(value).upper()
            
        # Validar contra enum class si se proporciona
        if enum_class and hasattr(enum_class, '__members__'):
            valid_values = [member.value for member in enum_class.__members__.values()]
            if normalized not in valid_values:
                # Intentar buscar coincidencia case-insensitive
                for valid_value in valid_values:
                    if normalized == valid_value.upper():
                        return valid_value
                        
                raise ValueError(f"Valor '{value}' no es válido para {enum_class.__name__}. Valores permitidos: {valid_values}")
                
        return normalized
    
    @staticmethod
    def validate_transition(current_state: Any, new_state: Any, transitions_dict: dict) -> tuple[bool, str]:
        """
        Valida si una transición de estado es permitida
        
        Args:
            current_state: Estado actual
            new_state: Estado destino
            transitions_dict: Diccionario de transiciones permitidas
            
        Returns:
            Tuple (es_válida, mensaje_error)
        """
        current_normalized = EnumNormalizer.normalize_enum_value(current_state)
        new_normalized = EnumNormalizer.normalize_enum_value(new_state)
        
        allowed_transitions = transitions_dict.get(current_normalized, [])
        
        if new_normalized in allowed_transitions:
            return True, ""
        else:
            return False, f"Transición no permitida de '{current_normalized}' a '{new_normalized}'"
    
    @staticmethod
    def create_case_insensitive_filter(column, value: Any):
        """
        Crea filtro case-insensitive para SQLAlchemy
        
        Args:
            column: Columna de SQLAlchemy
            value: Valor a filtrar
            
        Returns:
            Condición de filtro case-insensitive
        """
        from sqlalchemy import func
        
        if value is None:
            return column.is_(None)
            
        normalized_value = EnumNormalizer.normalize_enum_value(value)
        return func.upper(column) == normalized_value