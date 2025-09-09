"""
Constantes centralizadas para transiciones de estado
Única fuente de verdad para todas las transiciones permitidas
"""

# Transiciones para Órdenes de Fabricación - sincronizados con models.py y BD
OF_TRANSITIONS = {
    "pendiente_aprobacion_diseño": ["aprobado"],
    "aprobado": ["enviado_a_fabricacion"],
    "enviado_a_fabricacion": ["seccionando", "aprobado"],
    "seccionando": ["enchapando", "enviado_a_fabricacion"],
    "enchapando": ["mecanizando", "seccionando"],
    "mecanizando": ["fabricacion_completa", "enchapando"],
    "fabricacion_completa": ["pendiente_de_embalar"],
    "pendiente_de_embalar": ["embalando"],
    "embalando": ["embalaje_listo", "pendiente_de_embalar"],
    "embalaje_listo": ["listo_para_despacho"],
    "listo_para_despacho": ["programado_para_despacho", "despachado"],
    "programado_para_despacho": ["despachado"],
    "despachado": []  # Estado final
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
    "seccionando": {
        "required_fields": ["cantidad_tableros"],
        "validation_message": "La cantidad de tableros es obligatoria para cambiar a estado SECCIONANDO"
    }
}

# Estados activos para dashboards y reportes - sincronizados con models.py y BD
OF_ACTIVE_STATES = [
    "pendiente_aprobacion_diseño", 
    "aprobado", 
    "enviado_a_fabricacion", 
    "seccionando",
    "enchapando", 
    "mecanizando"
]

OF_FACTORY_STATES = [
    "enviado_a_fabricacion", 
    "seccionando",
    "enchapando", 
    "mecanizando",
    "fabricacion_completa"
]

OF_PACKAGING_STATES = [
    "pendiente_de_embalar",
    "embalando", 
    "embalaje_listo"
]

OF_DISPATCH_STATES = [
    "listo_para_despacho",
    "programado_para_despacho",
    "despachado"
]