from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime, date
from enum import Enum

class EstadoProyectoEnum(str, Enum):
    PLANIFICACION = "planificacion"
    EN_DESARROLLO = "en_desarrollo"
    PAUSADO = "pausado"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

class ProyectoBase(BaseModel):
    cliente_id: int = Field(..., description="ID del cliente")
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del proyecto")
    descripcion: Optional[str] = Field(None, description="Descripción del proyecto")
    estado: EstadoProyectoEnum = Field(EstadoProyectoEnum.PLANIFICACION, description="Estado del proyecto")
    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio")
    fecha_fin_estimada: Optional[date] = Field(None, description="Fecha de fin estimada")
    fecha_fin_real: Optional[date] = Field(None, description="Fecha de fin real")
    responsable: Optional[str] = Field(None, description="ID del usuario responsable")
    notas: Optional[str] = Field(None, description="Notas adicionales")

    @validator('fecha_fin_estimada')
    def validate_fecha_fin_estimada(cls, v, values):
        if v and 'fecha_inicio' in values and values['fecha_inicio']:
            if v < values['fecha_inicio']:
                raise ValueError('La fecha de fin estimada debe ser posterior a la fecha de inicio')
        return v

    @validator('fecha_fin_real')
    def validate_fecha_fin_real(cls, v, values):
        if v and 'fecha_inicio' in values and values['fecha_inicio']:
            if v < values['fecha_inicio']:
                raise ValueError('La fecha de fin real debe ser posterior a la fecha de inicio')
        return v

class ProyectoCreate(ProyectoBase):
    pass

class ProyectoUpdate(BaseModel):
    cliente_id: Optional[int] = None
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    estado: Optional[EstadoProyectoEnum] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_estimada: Optional[date] = None
    fecha_fin_real: Optional[date] = None
    responsable: Optional[str] = None
    notas: Optional[str] = None

class ProyectoResponse(ProyectoBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    cliente_nombre: Optional[str] = None
    responsable_nombre: Optional[str] = None

    class Config:
        from_attributes = True

class ProyectoSearchFilters(BaseModel):
    cliente_id: Optional[int] = Field(None, description="Filtrar por cliente")
    nombre: Optional[str] = Field(None, description="Buscar por nombre")
    estado: Optional[EstadoProyectoEnum] = Field(None, description="Filtrar por estado")
    responsable: Optional[str] = Field(None, description="Filtrar por responsable")
    fecha_inicio_desde: Optional[date] = Field(None, description="Fecha de inicio desde")
    fecha_inicio_hasta: Optional[date] = Field(None, description="Fecha de inicio hasta")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")
