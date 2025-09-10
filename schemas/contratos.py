from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

class TipoDocumentoEnum(str, Enum):
    CONTRATO = "CONTRATO"
    ORDEN_COMPRA = "ORDEN_COMPRA"

class EstadoContratoEnum(str, Enum):
    BORRADOR = "BORRADOR"
    VIGENTE = "VIGENTE"
    CERRADO = "CERRADO"
    ANULADO = "ANULADO"

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
    
    # Campos para soporte UF
    monto_total_uf: Optional[Decimal] = Field(None, description="Monto total original en UF")
    valor_uf_conversion: Optional[Decimal] = Field(None, description="Valor UF usado para conversión")
    fecha_conversion_uf: Optional[date] = Field(None, description="Fecha de conversión UF a CLP")
    moneda_original: Optional[str] = Field(None, max_length=3, description="Moneda original de entrada (UF o CLP)")
    
    estado: EstadoContratoEnum = Field(EstadoContratoEnum.BORRADOR, description="Estado del contrato")
    fecha_emision: Optional[date] = Field(None, description="Fecha de emisión")
    fecha_vencimiento: Optional[date] = Field(None, description="Fecha de vencimiento")
    condiciones_pago: Optional[str] = Field(None, description="Condiciones de pago")
    notas: Optional[str] = Field(None, description="Notas adicionales")
    categoria_ids: List[int] = Field(default_factory=list, description="IDs de categorías de muebles")

    @validator('monto_total')
    def validate_monto_total(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto total debe ser mayor a 0')
        return v
    
    @validator('monto_total_uf')
    def validate_monto_total_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto total en UF debe ser mayor a 0')
        return v
    
    @validator('moneda_original')
    def validate_moneda_original(cls, v):
        if v is not None and v not in ['UF', 'CLP']:
            raise ValueError('La moneda original debe ser UF o CLP')
        return v

    @validator('fecha_vencimiento')
    def validate_fecha_vencimiento(cls, v, values):
        if v and 'fecha_emision' in values and values['fecha_emision']:
            if v < values['fecha_emision']:
                raise ValueError('La fecha de vencimiento debe ser posterior a la fecha de emisión')
        return v

    @model_validator(mode='after')
    def validate_uf_consistency(self):
        """Validar consistencia de campos UF y prevenir doble entrada de monedas"""
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente
        has_clp_amount = self.monto_total is not None
        has_uf_amount = self.monto_total_uf is not None
        
        if has_clp_amount and has_uf_amount:
            raise ValueError('No se puede proporcionar monto_total (CLP) y monto_total_uf simultáneamente. '
                           'Ingrese el monto en una sola moneda: CLP o UF.')
        
        # Si se proporciona monto en UF o moneda original es UF, validar campos requeridos
        is_uf_currency = self.moneda_original == 'UF'
        
        if has_uf_amount or is_uf_currency:
            if self.valor_uf_conversion is None:
                raise ValueError('valor_uf_conversion es requerido cuando se proporciona monto_total_uf o moneda_original=UF')
            if self.fecha_conversion_uf is None:
                raise ValueError('fecha_conversion_uf es requerida cuando se proporciona monto_total_uf o moneda_original=UF')
            if self.valor_uf_conversion <= 0:
                raise ValueError('valor_uf_conversion debe ser mayor a 0')
        
        # Prevenir estados inconsistentes
        if has_uf_amount and self.moneda_original and self.moneda_original != 'UF':
            raise ValueError('Si se proporciona monto_total_uf, moneda_original debe ser UF o None')
        
        if is_uf_currency and not has_uf_amount:
            raise ValueError('Si moneda_original es UF, debe proporcionarse monto_total_uf')
        
        return self

class ContratoCreate(ContratoBase):
    @model_validator(mode='after')
    def validate_create_requirements(self):
        """Validaciones específicas para creación de contratos"""
        # Al menos uno de los montos debe estar presente (validación ya incluye exclusividad mutua en ContratoBase)
        has_clp_amount = self.monto_total is not None
        has_uf_amount = self.monto_total_uf is not None
        
        if not has_clp_amount and not has_uf_amount:
            raise ValueError('Debe proporcionarse exactamente un monto: monto_total (CLP) o monto_total_uf (UF), no ambos')
        
        return self

class ContratoUpdate(BaseModel):
    proyecto_id: Optional[int] = None
    tipo_documento: Optional[TipoDocumentoEnum] = None
    numero_oc: Optional[str] = Field(None, min_length=1, max_length=50)
    monto_total: Optional[Decimal] = None
    moneda: Optional[str] = Field(None, max_length=3)
    
    # Campos UF para actualización
    monto_total_uf: Optional[Decimal] = None
    valor_uf_conversion: Optional[Decimal] = None
    fecha_conversion_uf: Optional[date] = None
    moneda_original: Optional[str] = Field(None, max_length=3)
    
    estado: Optional[EstadoContratoEnum] = None
    fecha_emision: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    condiciones_pago: Optional[str] = None
    notas: Optional[str] = None
    categoria_ids: Optional[List[int]] = None

    @validator('monto_total')
    def validate_monto_total(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto total debe ser mayor a 0')
        return v
    
    @validator('monto_total_uf')
    def validate_monto_total_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto total en UF debe ser mayor a 0')
        return v
    
    @validator('moneda_original')
    def validate_moneda_original(cls, v):
        if v is not None and v not in ['UF', 'CLP']:
            raise ValueError('La moneda original debe ser UF o CLP')
        return v

    @validator('fecha_vencimiento')
    def validate_fecha_vencimiento(cls, v, values):
        if v and 'fecha_emision' in values and values['fecha_emision']:
            if v < values['fecha_emision']:
                raise ValueError('La fecha de vencimiento debe ser posterior a la fecha de emisión')
        return v

    @model_validator(mode='after')
    def validate_uf_consistency_update(self):
        """Validar consistencia de campos UF en actualizaciones y prevenir doble entrada"""
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente en actualizaciones
        has_clp_amount = self.monto_total is not None
        has_uf_amount = self.monto_total_uf is not None
        
        if has_clp_amount and has_uf_amount:
            raise ValueError('No se puede actualizar monto_total (CLP) y monto_total_uf simultáneamente. '
                           'Actualice el monto en una sola moneda: CLP o UF.')
        
        # Solo validar si se están proporcionando campos UF
        is_uf_currency = self.moneda_original == 'UF'
        
        if has_uf_amount or is_uf_currency:
            if has_uf_amount and self.valor_uf_conversion is None:
                raise ValueError('valor_uf_conversion es requerido cuando se actualiza monto_total_uf')
            if has_uf_amount and self.fecha_conversion_uf is None:
                raise ValueError('fecha_conversion_uf es requerida cuando se actualiza monto_total_uf')
            if self.valor_uf_conversion is not None and self.valor_uf_conversion <= 0:
                raise ValueError('valor_uf_conversion debe ser mayor a 0')
        
        # Prevenir estados inconsistentes
        if has_uf_amount and self.moneda_original and self.moneda_original != 'UF':
            raise ValueError('Si se actualiza monto_total_uf, moneda_original debe ser UF o None')
        
        if is_uf_currency and not has_uf_amount:
            raise ValueError('Si se actualiza moneda_original a UF, debe proporcionarse monto_total_uf')
        
        return self

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
    categorias_mueble: List[dict] = Field(default_factory=list, description="Categorías de muebles")
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
    categoria_id: Optional[int] = Field(None, description="Filtrar por categoría")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")

# Schemas específicos para UF
class ContratoUfInput(BaseModel):
    """Schema para entrada de contratos con valores en UF"""
    proyecto_id: int = Field(..., description="ID del proyecto")
    tipo_documento: TipoDocumentoEnum = Field(TipoDocumentoEnum.CONTRATO, description="Tipo de documento")
    numero_oc: str = Field(..., min_length=1, max_length=50, description="Número de OC")
    monto_total_uf: Decimal = Field(..., gt=0, description="Monto total en UF")
    estado: EstadoContratoEnum = Field(EstadoContratoEnum.BORRADOR, description="Estado del contrato")
    fecha_emision: Optional[date] = Field(None, description="Fecha de emisión")
    fecha_vencimiento: Optional[date] = Field(None, description="Fecha de vencimiento")
    condiciones_pago: Optional[str] = Field(None, description="Condiciones de pago")
    notas: Optional[str] = Field(None, description="Notas adicionales")
    categoria_ids: List[int] = Field(default_factory=list, description="IDs de categorías de muebles")

class ContratoDisplayInfo(BaseModel):
    """Schema para mostrar información completa de contrato con UF"""
    id: int
    numero_oc: str
    monto_clp: Optional[Decimal] = Field(None, description="Monto en CLP almacenado")
    moneda: str
    fue_ingresado_en_uf: bool = Field(False, description="Indica si fue ingresado originalmente en UF")
    monto_uf_original: Optional[Decimal] = Field(None, description="Monto original en UF")
    monto_clp_actualizado: Optional[Decimal] = Field(None, description="Monto CLP con UF actual")
    valor_uf_conversion: Optional[Decimal] = Field(None, description="Valor UF usado en conversión original")
    valor_uf_actual: Optional[Decimal] = Field(None, description="Valor UF actual")
    fecha_conversion: Optional[date] = Field(None, description="Fecha de conversión original")
    variacion_uf: Optional[Decimal] = Field(None, description="Variación entre UF original y actual")

class UfConversionInfo(BaseModel):
    """Información sobre conversión UF"""
    uf_amount: Decimal
    uf_value: Decimal
    clp_amount: Decimal
    conversion_date: date
    conversion_timestamp: datetime
