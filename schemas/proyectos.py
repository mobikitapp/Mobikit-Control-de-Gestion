from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from decimal import Decimal


class EstadoComercialEnum(str, Enum):
    PENDIENTE_PRESUPUESTO = "PENDIENTE_PRESUPUESTO"
    PRESUPUESTADO = "PRESUPUESTADO"
    ADJUDICADO = "ADJUDICADO"
    EN_DESARROLLO = "EN_DESARROLLO"
    TERMINADO = "TERMINADO"
    PERDIDO = "PERDIDO"

class ProyectoBase(BaseModel):
    cliente_id: int = Field(..., description="ID del cliente")
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del proyecto")
    descripcion: Optional[str] = Field(None, description="Descripción del proyecto")
    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio")
    fecha_fin_estimada: Optional[date] = Field(None, description="Fecha de fin estimada")
    fecha_fin_real: Optional[date] = Field(None, description="Fecha de fin real")
    responsable: Optional[str] = Field(None, description="ID del usuario responsable")
    notas: Optional[str] = Field(None, description="Notas adicionales")
    
    # Campos comerciales
    vendedor_id: Optional[str] = Field(None, description="ID del vendedor")
    monto_provision_presupuestado: Optional[Decimal] = Field(None, description="Monto neto de venta por provisión (precio al cliente)")
    margen_venta_provision: Optional[Decimal] = Field(None, description="Margen de ganancia sobre provisión (%)")
    monto_instalacion_presupuestado: Optional[Decimal] = Field(None, description="Monto neto de venta por instalación (precio al cliente)")
    margen_venta_instalacion: Optional[Decimal] = Field(None, description="Margen de ganancia sobre instalación (%)")
    
    # Campos para soporte UF en presupuestos
    monto_provision_presupuestado_uf: Optional[Decimal] = Field(None, description="Monto provisión original en UF")
    monto_instalacion_presupuestado_uf: Optional[Decimal] = Field(None, description="Monto instalación original en UF")
    valor_uf_presupuesto: Optional[Decimal] = Field(None, description="Valor UF usado en presupuesto")
    fecha_conversion_presupuesto_uf: Optional[date] = Field(None, description="Fecha conversión presupuesto")
    moneda_original_presupuesto: Optional[str] = Field(None, max_length=3, description="Moneda original del presupuesto (UF o CLP)")
    
    fecha_presupuesto: Optional[date] = Field(None, description="Fecha del presupuesto")
    fecha_adjudicacion: Optional[date] = Field(None, description="Fecha de adjudicación")
    notas_comerciales: Optional[str] = Field(None, description="Notas comerciales")
    
    # Campos adicionales opcionales para vendedores
    tipo_proyecto: Optional[str] = Field(None, description="Tipo de proyecto (Social, Estándar, Especial)")
    tipo_vivienda: Optional[str] = Field(None, description="Tipo de vivienda (Casa, Departamento)")
    numero_viviendas: Optional[int] = Field(None, description="Número de viviendas", gt=0)
    ubicacion_obra: Optional[str] = Field(None, description="Ubicación de la obra", max_length=500)
    
    # Campo para integración con ERP Mobikit
    centro_costo: Optional[int] = Field(None, description="Centro de costo para enlace con ERP Mobikit")

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
    
    @validator('monto_provision_presupuestado')
    def validate_monto_provision_clp(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de provisión debe ser mayor a 0')
        return v
    
    @validator('monto_instalacion_presupuestado')
    def validate_monto_instalacion_clp(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de instalación debe ser mayor a 0')
        return v
    
    @validator('monto_provision_presupuestado_uf')
    def validate_monto_provision_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de provisión en UF debe ser mayor a 0')
        return v
    
    @validator('monto_instalacion_presupuestado_uf')
    def validate_monto_instalacion_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de instalación en UF debe ser mayor a 0')
        return v
    
    @validator('moneda_original_presupuesto')
    def validate_moneda_original_presupuesto(cls, v):
        if v is not None and v not in ['UF', 'CLP']:
            raise ValueError('La moneda original del presupuesto debe ser UF o CLP')
        return v

    @model_validator(mode='after')
    def validate_uf_presupuesto_consistency(self):
        """Validar consistencia de campos UF en presupuestos y prevenir doble entrada de monedas"""
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente para provision
        has_provision_clp = self.monto_provision_presupuestado is not None
        has_provision_uf = self.monto_provision_presupuestado_uf is not None
        
        if has_provision_clp and has_provision_uf:
            raise ValueError('No se puede proporcionar monto_provision_presupuestado (CLP) y monto_provision_presupuestado_uf simultáneamente. '
                           'Ingrese el monto de provisión en una sola moneda: CLP o UF.')
        
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente para instalación
        has_instalacion_clp = self.monto_instalacion_presupuestado is not None
        has_instalacion_uf = self.monto_instalacion_presupuestado_uf is not None
        
        if has_instalacion_clp and has_instalacion_uf:
            raise ValueError('No se puede proporcionar monto_instalacion_presupuestado (CLP) y monto_instalacion_presupuestado_uf simultáneamente. '
                           'Ingrese el monto de instalación en una sola moneda: CLP o UF.')
        
        # Verificar si hay montos en UF
        is_uf_currency = self.moneda_original_presupuesto == 'UF'
        
        # Si hay cualquier monto UF o moneda original es UF, validar campos requeridos
        if has_provision_uf or has_instalacion_uf or is_uf_currency:
            if self.valor_uf_presupuesto is None:
                raise ValueError('valor_uf_presupuesto es requerido cuando se proporcionan montos en UF')
            if self.fecha_conversion_presupuesto_uf is None:
                raise ValueError('fecha_conversion_presupuesto_uf es requerida cuando se proporcionan montos en UF')
            if self.valor_uf_presupuesto <= 0:
                raise ValueError('valor_uf_presupuesto debe ser mayor a 0')
        
        # Prevenir estados inconsistentes
        if (has_provision_uf or has_instalacion_uf) and self.moneda_original_presupuesto and self.moneda_original_presupuesto != 'UF':
            raise ValueError('Si se proporcionan montos en UF, moneda_original_presupuesto debe ser UF o None')
        
        if is_uf_currency and not has_provision_uf and not has_instalacion_uf:
            raise ValueError('Si moneda_original_presupuesto es UF, debe proporcionarse al menos un monto en UF')
        
        return self

class ProyectoCreate(ProyectoBase):
    @model_validator(mode='after')
    def validate_create_requirements(self):
        """Validaciones específicas para creación de proyectos con presupuestos"""
        # Si hay datos comerciales, validar que al menos haya un monto (validación ya incluye exclusividad mutua en ProyectoBase)
        has_commercial_data = (
            self.vendedor_id is not None or 
            self.fecha_presupuesto is not None or 
            self.notas_comerciales is not None or
            self.margen_venta_provision is not None or
            self.margen_venta_instalacion is not None
        )
        
        if has_commercial_data:
            has_clp_amounts = (
                self.monto_provision_presupuestado is not None or 
                self.monto_instalacion_presupuestado is not None
            )
            has_uf_amounts = (
                self.monto_provision_presupuestado_uf is not None or 
                self.monto_instalacion_presupuestado_uf is not None
            )
            
            if not has_clp_amounts and not has_uf_amounts:
                raise ValueError('Si se proporcionan datos comerciales, debe incluirse al menos un monto presupuestado. '
                               'Use CLP o UF para cada monto, no ambos simultáneamente.')
        
        return self

class ProyectoUpdate(BaseModel):
    cliente_id: Optional[int] = None
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_estimada: Optional[date] = None
    fecha_fin_real: Optional[date] = None
    responsable: Optional[str] = None
    notas: Optional[str] = None
    
    # Campos comerciales
    vendedor_id: Optional[str] = None
    monto_provision_presupuestado: Optional[Decimal] = None
    margen_venta_provision: Optional[Decimal] = None
    monto_instalacion_presupuestado: Optional[Decimal] = None
    margen_venta_instalacion: Optional[Decimal] = None
    
    # Campos UF para actualización
    monto_provision_presupuestado_uf: Optional[Decimal] = None
    monto_instalacion_presupuestado_uf: Optional[Decimal] = None
    valor_uf_presupuesto: Optional[Decimal] = None
    fecha_conversion_presupuesto_uf: Optional[date] = None
    moneda_original_presupuesto: Optional[str] = Field(None, max_length=3)
    
    fecha_presupuesto: Optional[date] = None
    fecha_adjudicacion: Optional[date] = None
    notas_comerciales: Optional[str] = None
    
    # Campos adicionales opcionales para vendedores
    tipo_proyecto: Optional[str] = None
    tipo_vivienda: Optional[str] = None
    numero_viviendas: Optional[int] = Field(None, gt=0)
    ubicacion_obra: Optional[str] = Field(None, max_length=500)
    
    # Campo para integración con ERP Mobikit
    centro_costo: Optional[int] = None

    @validator('monto_provision_presupuestado')
    def validate_monto_provision_clp(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de provisión debe ser mayor a 0')
        return v
    
    @validator('monto_instalacion_presupuestado')
    def validate_monto_instalacion_clp(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de instalación debe ser mayor a 0')
        return v
    
    @validator('monto_provision_presupuestado_uf')
    def validate_monto_provision_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de provisión en UF debe ser mayor a 0')
        return v
    
    @validator('monto_instalacion_presupuestado_uf')
    def validate_monto_instalacion_uf(cls, v):
        if v is not None and v <= 0:
            raise ValueError('El monto de instalación en UF debe ser mayor a 0')
        return v
    
    @validator('moneda_original_presupuesto')
    def validate_moneda_original_presupuesto(cls, v):
        if v is not None and v not in ['UF', 'CLP']:
            raise ValueError('La moneda original del presupuesto debe ser UF o CLP')
        return v

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

    @model_validator(mode='after')
    def validate_uf_presupuesto_consistency_update(self):
        """Validar consistencia de campos UF en actualizaciones de presupuestos y prevenir doble entrada"""
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente para provisión en actualizaciones
        has_provision_clp = self.monto_provision_presupuestado is not None
        has_provision_uf = self.monto_provision_presupuestado_uf is not None
        
        if has_provision_clp and has_provision_uf:
            raise ValueError('No se puede actualizar monto_provision_presupuestado (CLP) y monto_provision_presupuestado_uf simultáneamente. '
                           'Actualice el monto de provisión en una sola moneda: CLP o UF.')
        
        # PREVENIR DOBLE ENTRADA: No permitir CLP y UF simultáneamente para instalación en actualizaciones
        has_instalacion_clp = self.monto_instalacion_presupuestado is not None
        has_instalacion_uf = self.monto_instalacion_presupuestado_uf is not None
        
        if has_instalacion_clp and has_instalacion_uf:
            raise ValueError('No se puede actualizar monto_instalacion_presupuestado (CLP) y monto_instalacion_presupuestado_uf simultáneamente. '
                           'Actualice el monto de instalación en una sola moneda: CLP o UF.')
        
        # Solo validar si se están proporcionando campos UF
        is_uf_currency = self.moneda_original_presupuesto == 'UF'
        
        if has_provision_uf or has_instalacion_uf or is_uf_currency:
            if (has_provision_uf or has_instalacion_uf) and self.valor_uf_presupuesto is None:
                raise ValueError('valor_uf_presupuesto es requerido cuando se actualizan montos en UF')
            if (has_provision_uf or has_instalacion_uf) and self.fecha_conversion_presupuesto_uf is None:
                raise ValueError('fecha_conversion_presupuesto_uf es requerida cuando se actualizan montos en UF')
            if self.valor_uf_presupuesto is not None and self.valor_uf_presupuesto <= 0:
                raise ValueError('valor_uf_presupuesto debe ser mayor a 0')
        
        # Prevenir estados inconsistentes
        if (has_provision_uf or has_instalacion_uf) and self.moneda_original_presupuesto and self.moneda_original_presupuesto != 'UF':
            raise ValueError('Si se actualizan montos en UF, moneda_original_presupuesto debe ser UF o None')
        
        if is_uf_currency and not has_provision_uf and not has_instalacion_uf:
            raise ValueError('Si se actualiza moneda_original_presupuesto a UF, debe proporcionarse al menos un monto en UF')
        
        return self

class ProyectoResponse(ProyectoBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    cliente_nombre: Optional[str] = None
    responsable_nombre: Optional[str] = None
    vendedor_nombre: Optional[str] = None
    estado_comercial: Optional[EstadoComercialEnum] = None
    categorias_mueble: List[dict] = Field(default_factory=list, description="Categorías de muebles asociadas")
    tiene_datos_comerciales: bool = Field(False, description="Indica si tiene datos comerciales completos")

    class Config:
        from_attributes = True

class ProyectoSearchFilters(BaseModel):
    cliente_id: Optional[int] = Field(None, description="Filtrar por cliente")
    nombre: Optional[str] = Field(None, description="Buscar por nombre")
    responsable: Optional[str] = Field(None, description="Filtrar por responsable")
    fecha_inicio_desde: Optional[date] = Field(None, description="Fecha de inicio desde")
    fecha_inicio_hasta: Optional[date] = Field(None, description="Fecha de inicio hasta")
    vendedor_id: Optional[str] = Field(None, description="Filtrar por vendedor")
    estado_comercial: Optional[EstadoComercialEnum] = Field(None, description="Filtrar por estado comercial")
    categoria_id: Optional[int] = Field(None, description="Filtrar por categoría")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")

# Schemas específicos para UF
class ProyectoUfInput(BaseModel):
    """Schema para entrada de proyectos con presupuestos en UF"""
    cliente_id: int = Field(..., description="ID del cliente")
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del proyecto")
    descripcion: Optional[str] = Field(None, description="Descripción del proyecto")
    vendedor_id: Optional[str] = Field(None, description="ID del vendedor")
    
    # Presupuestos en UF
    monto_provision_presupuestado_uf: Optional[Decimal] = Field(None, gt=0, description="Monto provisión en UF")
    monto_instalacion_presupuestado_uf: Optional[Decimal] = Field(None, gt=0, description="Monto instalación en UF")
    margen_venta_provision: Optional[Decimal] = Field(None, description="Margen de ganancia sobre provisión (%)")
    margen_venta_instalacion: Optional[Decimal] = Field(None, description="Margen de ganancia sobre instalación (%)")
    
    fecha_presupuesto: Optional[date] = Field(None, description="Fecha del presupuesto")
    fecha_adjudicacion: Optional[date] = Field(None, description="Fecha de adjudicación")
    notas_comerciales: Optional[str] = Field(None, description="Notas comerciales")

class ProyectoPresupuestoDisplayInfo(BaseModel):
    """Schema para mostrar información completa de presupuesto con UF"""
    id: int
    nombre: str
    
    # Información provisión
    provision_clp: Optional[Decimal] = Field(None, description="Monto provisión en CLP almacenado")
    provision_fue_ingresado_en_uf: bool = Field(False, description="Provisión ingresada en UF")
    provision_uf_original: Optional[Decimal] = Field(None, description="Provisión original en UF")
    provision_clp_actualizado: Optional[Decimal] = Field(None, description="Provisión CLP con UF actual")
    
    # Información instalación
    instalacion_clp: Optional[Decimal] = Field(None, description="Monto instalación en CLP almacenado")
    instalacion_fue_ingresado_en_uf: bool = Field(False, description="Instalación ingresada en UF")
    instalacion_uf_original: Optional[Decimal] = Field(None, description="Instalación original en UF")
    instalacion_clp_actualizado: Optional[Decimal] = Field(None, description="Instalación CLP con UF actual")
    
    # Información UF general
    valor_uf_presupuesto: Optional[Decimal] = Field(None, description="Valor UF usado en presupuesto original")
    valor_uf_actual: Optional[Decimal] = Field(None, description="Valor UF actual")
    fecha_conversion: Optional[date] = Field(None, description="Fecha de conversión original")
    variacion_uf: Optional[Decimal] = Field(None, description="Variación entre UF original y actual")
    
    # Totales
    total_clp: Decimal = Field(..., description="Total presupuestado en CLP")
    total_clp_actualizado: Decimal = Field(..., description="Total con UF actualizada")
