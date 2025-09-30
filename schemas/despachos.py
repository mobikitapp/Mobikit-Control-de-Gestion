from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from decimal import Decimal

class EstadoDespachoEnum(str, Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ENTREGADO = "ENTREGADO"
    OBSERVADO = "OBSERVADO"

class TipoAdjuntoDespachoEnum(str, Enum):
    GUIA = "guia"
    ACTA = "acta"
    FOTO = "foto"

class TipoDespachoEnum(str, Enum):
    TOTAL = "TOTAL"
    PARCIAL = "PARCIAL"

class EstadoDespachoBodegaEnum(str, Enum):
    LISTO_PARA_DESPACHO = "listo_para_despacho"
    PARCIALMENTE_DESPACHADO = "parcialmente_despachado"
    COMPLETAMENTE_DESPACHADO = "completamente_despachado"

class DespachoOrdenFabricacionBase(BaseModel):
    orden_fabricacion_id: int = Field(..., description="ID de la orden de fabricación")
    tipo_despacho: TipoDespachoEnum = Field(..., description="Tipo de despacho (total o parcial)")
    cantidad_despachada: Decimal = Field(..., gt=0, description="Cantidad a despachar")
    cantidad_total: Decimal = Field(..., gt=0, description="Cantidad total de la OF")
    observaciones: Optional[str] = Field(None, description="Observaciones específicas de esta OF")

    @validator('cantidad_despachada')
    def validate_cantidad_despachada(cls, v, values):
        if 'cantidad_total' in values and v > values['cantidad_total']:
            raise ValueError('La cantidad despachada no puede ser mayor a la cantidad total')
        return v

class DespachoOrdenFabricacionCreate(DespachoOrdenFabricacionBase):
    pass

class DespachoOrdenFabricacionResponse(DespachoOrdenFabricacionBase):
    id: int
    despacho_id: int
    created_at: datetime
    created_by: Optional[str]
    of_codigo: Optional[str] = None
    porcentaje_despachado: Optional[float] = None
    cantidad_pendiente: Optional[Decimal] = None

    class Config:
        from_attributes = True

class DespachoBase(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    contrato_id: Optional[int] = Field(None, description="ID del contrato (opcional)")
    hito_entrega_id: Optional[int] = Field(None, description="ID del hito de entrega")
    numero_despacho: Optional[str] = Field(None, max_length=50, description="Número de despacho (se auto-genera si no se proporciona)")
    glosa: str = Field(..., min_length=1, max_length=500, description="Glosa del despacho (obligatorio)")
    estado: EstadoDespachoEnum = Field(EstadoDespachoEnum.PROGRAMADO, description="Estado del despacho")
    fecha_programada: Optional[date] = Field(None, description="Fecha programada")
    fecha_envio: Optional[datetime] = Field(None, description="Fecha de envío")
    destino: str = Field(..., min_length=1, description="Destino del despacho")
    contacto_destino: Optional[str] = Field(None, max_length=200, description="Contacto en destino")
    telefono_contacto: Optional[str] = Field(None, max_length=50, description="Teléfono de contacto")
    observaciones: Optional[str] = Field(None, description="Observaciones")
    responsable_nombre: Optional[str] = Field(None, max_length=200, description="Nombre del responsable")
    numero_guias_despacho: Optional[str] = Field(None, max_length=255, description="Número de guías de despacho (opcional)")
    archivado: bool = Field(False, description="Indica si el despacho está archivado")

    @validator('fecha_envio')
    def validate_fecha_envio(cls, v, values):
        if v and 'fecha_programada' in values and values['fecha_programada']:
            if v.date() < values['fecha_programada']:
                raise ValueError('La fecha de envío no puede ser anterior a la fecha programada')
        return v


class DespachoCreate(DespachoBase):
    ordenes_fabricacion: List[DespachoOrdenFabricacionCreate] = Field(default=[], description="Lista de órdenes de fabricación a incluir")

class DespachoUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    contrato_id: Optional[int] = None
    hito_entrega_id: Optional[int] = None
    numero_despacho: Optional[str] = Field(None, max_length=50)
    glosa: Optional[str] = Field(None, min_length=1, max_length=500)
    estado: Optional[EstadoDespachoEnum] = None
    fecha_programada: Optional[date] = None
    fecha_envio: Optional[datetime] = None
    destino: Optional[str] = Field(None, min_length=1)
    contacto_destino: Optional[str] = Field(None, max_length=200)
    telefono_contacto: Optional[str] = Field(None, max_length=50)
    observaciones: Optional[str] = None
    responsable_nombre: Optional[str] = Field(None, max_length=200)
    numero_guias_despacho: Optional[str] = Field(None, max_length=255)
    archivado: Optional[bool] = None
    ordenes_fabricacion: Optional[List[DespachoOrdenFabricacionCreate]] = None

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
    hito_entrega_descripcion: Optional[str] = None
    hito_entrega_fecha: Optional[date] = None
    ordenes_fabricacion_detalle: List[DespachoOrdenFabricacionResponse] = []
    adjuntos: List[DespachoAdjuntoResponse] = []

    class Config:
        from_attributes = True

class DespachoSearchFilters(BaseModel):
    proyecto_id: Optional[int] = Field(None, description="Filtrar por proyecto")
    contrato_id: Optional[int] = Field(None, description="Filtrar por contrato")
    hito_entrega_id: Optional[int] = Field(None, description="Filtrar por hito de entrega")
    numero_despacho: Optional[str] = Field(None, description="Buscar por número de despacho")
    estado: Optional[EstadoDespachoEnum] = Field(None, description="Filtrar por estado")
    responsable_nombre: Optional[str] = Field(None, description="Filtrar por responsable")
    fecha_programada_desde: Optional[date] = Field(None, description="Fecha programada desde")
    fecha_programada_hasta: Optional[date] = Field(None, description="Fecha programada hasta")
    archivado: Optional[bool] = Field(None, description="Filtrar por archivado (None=excluir archivados, True=solo archivados, False=solo no archivados)")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")

# Nuevos schemas para planificación de despachos
class HitoEntregaDespacho(BaseModel):
    id: int
    contrato_id: int
    contrato_numero_oc: str
    descripcion: str
    fecha_entrega: date
    estado: str
    despacho_creado: bool
    despacho_id: Optional[int] = None
    ordenes_fabricacion_disponibles: List[dict] = []

    class Config:
        from_attributes = True

class ProyectoConHitos(BaseModel):
    id: int
    nombre: str
    hitos_entrega: List[HitoEntregaDespacho] = []

    class Config:
        from_attributes = True

class ClienteConProyectos(BaseModel):
    id: int
    nombre: str
    proyectos: List[ProyectoConHitos] = []

    class Config:
        from_attributes = True

class PlanificacionDespachosResponse(BaseModel):
    clientes: List[ClienteConProyectos] = []
    total_hitos_pendientes: int
    total_hitos_proximos: int  # próximos 7 días

    class Config:
        from_attributes = True

class CambioEstadoDespacho(BaseModel):
    nuevo_estado: EstadoDespachoEnum = Field(..., description="Nuevo estado del despacho")
    observaciones: Optional[str] = Field(None, description="Observaciones del cambio de estado")
