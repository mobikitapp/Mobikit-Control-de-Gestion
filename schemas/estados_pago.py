
from enum import Enum
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class EstadoPagoEnum(str, Enum):
    PENDIENTE = 'PENDIENTE'
    FACTURADO = 'FACTURADO'
    PAGADO = 'PAGADO'
    PARCIAL = 'PARCIAL'
    CANCELADO = 'CANCELADO'

class EstadoPendienteFacturar(str, Enum):
    PENDIENTE = 'PENDIENTE'
    FACTURADO = 'FACTURADO'
    PAGADO = 'PAGADO'

class TipoEstadoPago(str, Enum):
    ESTADO_PAGO_CONTRATO = 'ESTADO_PAGO_CONTRATO'
    PENDIENTE_FACTURAR = 'PENDIENTE_FACTURAR'

class EstadoPagoBase(BaseModel):
    contrato_id: int
    descripcion: str
    porcentaje_avance: Decimal
    monto_estado_pago: Decimal
    fecha_programada: Optional[date] = None
    observaciones: Optional[str] = None
    
class EstadoPagoCreate(EstadoPagoBase):
    pass

class EstadoPagoUpdate(BaseModel):
    descripcion: Optional[str] = None
    porcentaje_avance: Optional[Decimal] = None
    monto_estado_pago: Optional[Decimal] = None
    fecha_programada: Optional[date] = None
    fecha_pago: Optional[date] = None
    observaciones: Optional[str] = None
    estado: Optional[EstadoPagoEnum] = None
    facturado: Optional[bool] = None
    numero_factura: Optional[str] = None
