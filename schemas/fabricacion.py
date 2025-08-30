from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class EstadoOFEnum(str, Enum):
    PLANIFICADA = "planificada"
    EN_PRODUCCION = "en_produccion"
    QA = "qa"
    TERMINADA = "terminada"
    ENTREGADA = "entregada"

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
    codigo: str = Field(..., min_length=1, max_length=50, description="Código de la OF")
    descripcion: Optional[str] = Field(None, description="Descripción de la OF")
    estado: EstadoOFEnum = Field(EstadoOFEnum.PLANIFICADA, description="Estado de la OF")
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

class OrdenFabricacionCreate(OrdenFabricacionBase):
    items: List[OrdenFabricacionItemCreate] = Field([], description="Items de la OF")

class OrdenFabricacionUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    contrato_id: Optional[int] = None
    codigo: Optional[str] = Field(None, min_length=1, max_length=50)
    descripcion: Optional[str] = None
    estado: Optional[EstadoOFEnum] = None
    fecha_planificada: Optional[date] = None
    fecha_inicio: Optional[datetime] = None
    fecha_qc: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    responsable: Optional[str] = None
    notas: Optional[str] = None

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
