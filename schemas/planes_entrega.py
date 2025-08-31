from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum

class EstadoHitoEntregaEnum(str, Enum):
    PENDIENTE = "pendiente"
    COMPLETADO = "completado"
    ATRASADO = "atrasado"

class HitoEntregaBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200, description="Título del hito")
    descripcion: Optional[str] = Field(None, description="Descripción del hito")
    fecha_programada: date = Field(..., description="Fecha programada del hito")
    orden: int = Field(1, ge=1, description="Orden del hito en el plan")

class HitoEntregaCreate(HitoEntregaBase):
    pass

class HitoEntregaUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    fecha_programada: Optional[date] = None
    orden: Optional[int] = Field(None, ge=1)
    estado: Optional[EstadoHitoEntregaEnum] = None
    notas_completado: Optional[str] = None

class HitoEntregaResponse(HitoEntregaBase):
    id: int
    plan_entrega_id: int
    estado: EstadoHitoEntregaEnum
    fecha_completado: Optional[datetime] = None
    notas_completado: Optional[str] = None
    completado_por: Optional[str] = None
    completado_por_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True

class PlanEntregaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del plan de entrega")
    descripcion: Optional[str] = Field(None, description="Descripción del plan")

class PlanEntregaCreate(PlanEntregaBase):
    contrato_id: int = Field(..., description="ID del contrato")
    hitos: List[HitoEntregaCreate] = Field(default_factory=list, description="Hitos del plan")

    @validator('hitos')
    def validate_hitos(cls, v):
        if len(v) == 0:
            raise ValueError('Debe incluir al menos un hito de entrega')
        
        # Validar que no hayan órdenes duplicados
        ordenes = [hito.orden for hito in v]
        if len(ordenes) != len(set(ordenes)):
            raise ValueError('No puede haber hitos con el mismo orden')
        
        return v

class PlanEntregaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class PlanEntregaResponse(PlanEntregaBase):
    id: int
    contrato_id: int
    activo: bool
    hitos: List[HitoEntregaResponse] = []
    
    # Propiedades calculadas
    total_hitos: int = 0
    hitos_completados: int = 0
    progreso_porcentaje: float = 0.0
    proximo_hito: Optional[HitoEntregaResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True

class PlanEntregaSearchFilters(BaseModel):
    contrato_id: Optional[int] = None
    estado_hito: Optional[EstadoHitoEntregaEnum] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    activo: Optional[bool] = True
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)

class CompletarHitoRequest(BaseModel):
    notas_completado: Optional[str] = Field(None, description="Notas al completar el hito")