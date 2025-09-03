from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class EstadoDespachoEnum(str, Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ENTREGADO = "ENTREGADO"
    OBSERVADO = "OBSERVADO"

class TipoAdjuntoDespachoEnum(str, Enum):
    GUIA = "guia"
    ACTA = "acta"
    FOTO = "foto"

class DespachoBase(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    contrato_id: Optional[int] = Field(None, description="ID del contrato (opcional)")
    of_id: Optional[int] = Field(None, description="ID de la OF (opcional)")
    numero_despacho: str = Field(..., min_length=1, max_length=50, description="Número de despacho")
    estado: EstadoDespachoEnum = Field(EstadoDespachoEnum.PROGRAMADO, description="Estado del despacho")
    fecha_programada: Optional[date] = Field(None, description="Fecha programada")
    fecha_envio: Optional[datetime] = Field(None, description="Fecha de envío")
    destino: str = Field(..., min_length=1, description="Destino del despacho")
    contacto_destino: Optional[str] = Field(None, max_length=200, description="Contacto en destino")
    telefono_contacto: Optional[str] = Field(None, max_length=50, description="Teléfono de contacto")
    observaciones: Optional[str] = Field(None, description="Observaciones")
    responsable_nombre: Optional[str] = Field(None, max_length=200, description="Nombre del responsable")

    @validator('fecha_envio')
    def validate_fecha_envio(cls, v, values):
        if v and 'fecha_programada' in values and values['fecha_programada']:
            if v.date() < values['fecha_programada']:
                raise ValueError('La fecha de envío no puede ser anterior a la fecha programada')
        return v


class DespachoCreate(DespachoBase):
    pass

class DespachoUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    contrato_id: Optional[int] = None
    of_id: Optional[int] = None
    numero_despacho: Optional[str] = Field(None, min_length=1, max_length=50)
    estado: Optional[EstadoDespachoEnum] = None
    fecha_programada: Optional[date] = None
    fecha_envio: Optional[datetime] = None
    destino: Optional[str] = Field(None, min_length=1)
    contacto_destino: Optional[str] = Field(None, max_length=200)
    telefono_contacto: Optional[str] = Field(None, max_length=50)
    observaciones: Optional[str] = None
    responsable_nombre: Optional[str] = Field(None, max_length=200)

class DespachoAdjuntoBase(BaseModel):
    filename: str = Field(..., description="Nombre del archivo")
    mime_type: str = Field(..., description="Tipo MIME del archivo")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes")
    tipo: TipoAdjuntoDespachoEnum = Field(..., description="Tipo de adjunto")

class DespachoAdjuntoCreate(DespachoAdjuntoBase):
    storage_key: str = Field(..., description="Clave de almacenamiento")

class DespachoAdjuntoResponse(DespachoAdjuntoBase):
    id: int
    despacho_id: int
    storage_key: str
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True

class DespachoResponse(DespachoBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    proyecto_nombre: Optional[str] = None
    contrato_numero_oc: Optional[str] = None
    of_codigo: Optional[str] = None
    adjuntos: List[DespachoAdjuntoResponse] = []

    class Config:
        from_attributes = True

class DespachoSearchFilters(BaseModel):
    proyecto_id: Optional[int] = Field(None, description="Filtrar por proyecto")
    contrato_id: Optional[int] = Field(None, description="Filtrar por contrato")
    of_id: Optional[int] = Field(None, description="Filtrar por OF")
    numero_despacho: Optional[str] = Field(None, description="Buscar por número de despacho")
    estado: Optional[EstadoDespachoEnum] = Field(None, description="Filtrar por estado")
    responsable_nombre: Optional[str] = Field(None, description="Filtrar por responsable")
    fecha_programada_desde: Optional[date] = Field(None, description="Fecha programada desde")
    fecha_programada_hasta: Optional[date] = Field(None, description="Fecha programada hasta")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")

class CambioEstadoDespacho(BaseModel):
    nuevo_estado: EstadoDespachoEnum = Field(..., description="Nuevo estado del despacho")
    observaciones: Optional[str] = Field(None, description="Observaciones del cambio de estado")
