from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class TipoDocumentoEnum(str, Enum):
    CONTRATO = "contrato"
    ORDEN_COMPRA = "orden_compra"

class EstadoContratoEnum(str, Enum):
    BORRADOR = "borrador"
    VIGENTE = "vigente"
    CERRADO = "cerrado"
    ANULADO = "anulado"

class TipoAdjuntoEnum(str, Enum):
    CONTRATO = "contrato"
    PLANO = "plano"
    ESPECIFICACION = "especificacion"

class ContratoBase(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    tipo_documento: TipoDocumentoEnum = Field(TipoDocumentoEnum.CONTRATO, description="Tipo de documento")
    numero_oc: str = Field(..., min_length=1, max_length=50, description="Número de OC")
    monto_total: Optional[Decimal] = Field(None, description="Monto total del contrato")
    moneda: str = Field("CLP", max_length=3, description="Moneda del contrato")
    estado: EstadoContratoEnum = Field(EstadoContratoEnum.BORRADOR, description="Estado del contrato")
    fecha_emision: Optional[date] = Field(None, description="Fecha de emisión")
    fecha_vencimiento: Optional[date] = Field(None, description="Fecha de vencimiento")
    condiciones_pago: Optional[str] = Field(None, description="Condiciones de pago")
    notas: Optional[str] = Field(None, description="Notas adicionales")

    @validator('monto_total')
    def validate_monto_total(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto total debe ser mayor a 0')
        return v

    @validator('fecha_vencimiento')
    def validate_fecha_vencimiento(cls, v, values):
        if v and 'fecha_emision' in values and values['fecha_emision']:
            if v < values['fecha_emision']:
                raise ValueError('La fecha de vencimiento debe ser posterior a la fecha de emisión')
        return v

class ContratoCreate(ContratoBase):
    pass

class ContratoUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    tipo_documento: Optional[TipoDocumentoEnum] = None
    numero_oc: Optional[str] = Field(None, min_length=1, max_length=50)
    monto_total: Optional[Decimal] = None
    moneda: Optional[str] = Field(None, max_length=3)
    estado: Optional[EstadoContratoEnum] = None
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    condiciones_pago: Optional[str] = None
    notas: Optional[str] = None

class ContratoAdjuntoBase(BaseModel):
    filename: str = Field(..., description="Nombre del archivo")
    mime_type: str = Field(..., description="Tipo MIME del archivo")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes")
    tipo: TipoAdjuntoEnum = Field(..., description="Tipo de adjunto")

class ContratoAdjuntoCreate(ContratoAdjuntoBase):
    storage_key: str = Field(..., description="Clave de almacenamiento")

class ContratoAdjuntoResponse(ContratoAdjuntoBase):
    id: int
    contrato_id: int
    storage_key: str
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True

class ContratoResponse(ContratoBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    proyecto_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    adjuntos: List[ContratoAdjuntoResponse] = []

    class Config:
        from_attributes = True

class ContratoSearchFilters(BaseModel):
    proyecto_id: Optional[int] = Field(None, description="Filtrar por proyecto")
    tipo_documento: Optional[TipoDocumentoEnum] = Field(None, description="Filtrar por tipo de documento")
    numero_oc: Optional[str] = Field(None, description="Buscar por número de OC")
    estado: Optional[EstadoContratoEnum] = Field(None, description="Filtrar por estado")
    moneda: Optional[str] = Field(None, description="Filtrar por moneda")
    fecha_emision_desde: Optional[date] = Field(None, description="Fecha de emisión desde")
    fecha_emision_hasta: Optional[date] = Field(None, description="Fecha de emisión hasta")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")
