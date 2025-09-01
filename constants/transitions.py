"""
Constantes centralizadas para transiciones de estado
Única fuente de verdad para todas las transiciones permitidas
"""

# Transiciones para Órdenes de Fabricación
OF_TRANSITIONS = {
    "PENDIENTE_APROBACION_DISENO": ["APROBADO"],
    "APROBADO": ["ENVIADO_A_FABRICACION"],
    "ENVIADO_A_FABRICACION": ["SECCIONANDO", "APROBADO"],
    "SECCIONANDO": ["ENCHAPANDO", "ENVIADO_A_FABRICACION"],
    "ENCHAPANDO": ["MECANIZANDO", "SECCIONANDO"],
    "MECANIZANDO": ["FABRICACION_COMPLETA", "ENCHAPANDO"],
    "FABRICACION_COMPLETA": ["PENDIENTE_DE_EMBALAR"],
    "PENDIENTE_DE_EMBALAR": ["EMBALANDO"],
    "EMBALANDO": ["EMBALAJE_LISTO", "PENDIENTE_DE_EMBALAR"],
    "EMBALAJE_LISTO": ["LISTO_PARA_DESPACHO"],
    "LISTO_PARA_DESPACHO": ["DESPACHADO"],
    "DESPACHADO": []  # Estado final
}

# Transiciones para Contratos
CONTRATO_TRANSITIONS = {
    "BORRADOR": ["VIGENTE"],
    "VIGENTE": ["CERRADO", "ANULADO"],
    "CERRADO": [],
    "ANULADO": []
}

# Transiciones para Despachos
DESPACHO_TRANSITIONS = {
    "PROGRAMADO": ["EN_TRANSPORTE", "OBSERVADO"],
    "EN_TRANSPORTE": ["ENTREGADO", "OBSERVADO"],
    "ENTREGADO": [],
    "OBSERVADO": ["PROGRAMADO", "EN_TRANSPORTE"]
}

# Estados que requieren validaciones especiales
OF_SPECIAL_VALIDATIONS = {
    "SECCIONANDO": {
        "required_fields": ["cantidad_tableros"],
        "validation_message": "La cantidad de tableros es obligatoria para cambiar a estado SECCIONANDO"
    }
}

# Estados activos para dashboards y reportes
OF_ACTIVE_STATES = [
    "PENDIENTE_APROBACION_DISENO", 
    "APROBADO", 
    "ENVIADO_A_FABRICACION", 
    "SECCIONANDO",
    "ENCHAPANDO", 
    "MECANIZANDO"
]

OF_FACTORY_STATES = [
    "ENVIADO_A_FABRICACION", 
    "SECCIONANDO",
    "ENCHAPANDO", 
    "MECANIZANDO",
    "FABRICACION_COMPLETA"
]

OF_PACKAGING_STATES = [
    "PENDIENTE_DE_EMBALAR",
    "EMBALANDO", 
    "EMBALAJE_LISTO"
]

OF_DISPATCH_STATES = [
    "LISTO_PARA_DESPACHO",
    "DESPACHADO"
]