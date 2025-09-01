from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class EstadoOFEnum(str, Enum):
    # Estados de Pendientes de Fabricación - using exact values from models.py
    PENDIENTE_APROBACION_DISENO = "pendiente_aprobacion_diseno"
    APROBADO = "aprobado"
    # Estados de Fábrica
    ENVIADO_A_FABRICACION = "enviado_a_fabricacion"
    SECCIONANDO = "seccionando"
    ENCHAPANDO = "enchapando"
    MECANIZANDO = "mecanizando"
    FABRICACION_COMPLETA = "fabricacion_completa"
    # Estados de Embalaje
    PENDIENTE_DE_EMBALAR = "pendiente_de_embalar"
    EMBALANDO = "embalando"
    EMBALAJE_LISTO = "embalaje_listo"
    # Estados de Bodega
    LISTO_PARA_DESPACHO = "listo_para_despacho"
    # Estados de Despacho
    DESPACHADO = "despachado"

class OrdenFabricacionItemBase(BaseModel):
    sku_codigo: str = Field(..., min_length=1, max_length=50, description="SKU o código del item")
    descripcion: str = Field(..., min_length=1, max_length=255, description="Descripción del item")
    cantidad: Decimal = Field(..., gt=0, description="Cantidad")
    unidad: str = Field("UN", max_length=20, description="Unidad de medida")
    notas: Optional[str] = Field(None, description="Notas del item")

class OrdenFabricacionItemCreate(OrdenFabricacionItemBase):
    pass

class OrdenFabricacionItemUpdate(BaseModel):
    sku_codigo: Optional[str] = Field(None, min_length=1, max_length=50)
    descripcion: Optional[str] = Field(None, min_length=1, max_length=255)
    cantidad: Optional[Decimal] = Field(None, gt=0)
    unidad: Optional[str] = Field(None, max_length=20)
    notas: Optional[str] = None

class OrdenFabricacionItemResponse(OrdenFabricacionItemBase):
    id: int
    of_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class OrdenFabricacionBase(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    contrato_id: Optional[int] = Field(None, description="ID del contrato (opcional)")
    descripcion: Optional[str] = Field(None, description="Descripción de la OF")
    glosa: Optional[str] = Field(None, description="Glosa de la OF")
    cantidad_tableros: Optional[int] = Field(None, description="Cantidad de tableros")
    fecha_entrega_fabrica: Optional[date] = Field(None, description="Fecha de entrega de fábrica")
    fecha_planificada: Optional[date] = Field(None, description="Fecha planificada")
    fecha_inicio: Optional[datetime] = Field(None, description="Fecha de inicio")
    fecha_qc: Optional[datetime] = Field(None, description="Fecha de QC")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha de fin")
    responsable: Optional[str] = Field(None, description="ID del usuario responsable")
    notas: Optional[str] = Field(None, description="Notas adicionales")

    @validator('fecha_inicio')
    def validate_fecha_inicio(cls, v, values):
        if v and 'fecha_planificada' in values and values['fecha_planificada']:
            if v.date() < values['fecha_planificada']:
                raise ValueError('La fecha de inicio no puede ser anterior a la fecha planificada')
        return v

    @validator('fecha_qc')
    def validate_fecha_qc(cls, v, values):
        if v and 'fecha_inicio' in values and values['fecha_inicio']:
            if v < values['fecha_inicio']:
                raise ValueError('La fecha de QC debe ser posterior a la fecha de inicio')
        return v

    @validator('fecha_fin')
    def validate_fecha_fin(cls, v, values):
        if v and 'fecha_qc' in values and values['fecha_qc']:
            if v < values['fecha_qc']:
                raise ValueError('La fecha de fin debe ser posterior a la fecha de QC')
        return v
    
    @validator('cantidad_tableros', pre=True)
    def validate_cantidad_tableros(cls, v):
        # Handle empty string or None
        if v == '' or v is None:
            return None
        # Convert to int if it's a string
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                raise ValueError('La cantidad de tableros debe ser un número entero')
        # Validate positive number
        if v is not None and v <= 0:
            raise ValueError('La cantidad de tableros debe ser mayor a 0')
        return v

class OrdenFabricacionCreate(OrdenFabricacionBase):
    items: List[OrdenFabricacionItemCreate] = Field([], description="Items de la OF")
    
    class Config:
        # El estado siempre será PENDIENTE_APROBACION_DISENO al crear
        schema_extra = {
            "properties": {
                "estado": {
                    "const": "pendiente_aprobacion_diseno",
                    "description": "Estado fijo al crear (siempre pendiente_aprobacion_diseno)"
                }
            }
        }

class OrdenFabricacionUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    contrato_id: Optional[int] = None
    descripcion: Optional[str] = None
    glosa: Optional[str] = None
    cantidad_tableros: Optional[int] = None
    fecha_entrega_fabrica: Optional[date] = None
    estado: Optional[EstadoOFEnum] = None
    fecha_planificada: Optional[date] = None
    fecha_inicio: Optional[datetime] = None
    fecha_qc: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    responsable: Optional[str] = None
    notas: Optional[str] = None

    @validator('cantidad_tableros', pre=True)
    def validate_cantidad_tableros(cls, v):
        # Handle empty string or None
        if v == '' or v is None:
            return None
        # Convert to int if it's a string
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                raise ValueError('La cantidad de tableros debe ser un número entero')
        # Validate positive number
        if v is not None and v <= 0:
            raise ValueError('La cantidad de tableros debe ser mayor a 0')
        return v

    @validator('estado')
    def validate_estado_seccionando(cls, v, values):
        if v and v == EstadoOFEnum.SECCIONANDO:
            if 'cantidad_tableros' not in values or not values['cantidad_tableros']:
                raise ValueError('La cantidad de tableros es obligatoria para cambiar a estado seccionando')
        return v

class OrdenFabricacionResponse(OrdenFabricacionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    proyecto_nombre: Optional[str] = None
    contrato_numero_oc: Optional[str] = None
    responsable_nombre: Optional[str] = None
    items: List[OrdenFabricacionItemResponse] = []

    class Config:
        from_attributes = True

class OrdenFabricacionSearchFilters(BaseModel):
    proyecto_id: Optional[int] = Field(None, description="Filtrar por proyecto")
    contrato_id: Optional[int] = Field(None, description="Filtrar por contrato")
    codigo: Optional[str] = Field(None, description="Buscar por código")
    estado: Optional[EstadoOFEnum] = Field(None, description="Filtrar por estado")
    responsable: Optional[str] = Field(None, description="Filtrar por responsable")
    fecha_planificada_desde: Optional[date] = Field(None, description="Fecha planificada desde")
    fecha_planificada_hasta: Optional[date] = Field(None, description="Fecha planificada hasta")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")

class CambioEstadoOF(BaseModel):
    nuevo_estado: EstadoOFEnum = Field(..., description="Nuevo estado de la OF")
    notas: Optional[str] = Field(None, description="Notas del cambio de estado")
