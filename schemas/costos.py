"""
Schemas para validación de costos de proyectos
"""

from pydantic import BaseModel, Field, validator
from decimal import Decimal
from datetime import date
from typing import Optional, List
from models import CategoriaCosto


class CostoProyectoBase(BaseModel):
    """Schema base para costos de proyecto"""
    proyecto_id: int = Field(..., description="ID del proyecto")
    categoria: CategoriaCosto = Field(..., description="Categoría del costo")
    descripcion: str = Field(..., min_length=1, max_length=500, description="Descripción del costo")
    monto: Decimal = Field(..., gt=0, description="Monto del costo (debe ser mayor a 0)")
    fecha_registro: date = Field(..., description="Fecha del registro del costo")
    
    # Campos opcionales del ERP
    codigo_erp: Optional[str] = Field(None, max_length=50, description="Código de referencia del ERP")
    documento_referencia: Optional[str] = Field(None, max_length=100, description="Número de factura, guía, etc.")
    proveedor: Optional[str] = Field(None, max_length=200, description="Proveedor o empresa")

    @validator('monto')
    def validate_monto(cls, v):
        """Validar que el monto sea positivo y tenga máximo 2 decimales"""
        if v <= 0:
            raise ValueError('El monto debe ser mayor a 0')
        # Verificar máximo 2 decimales
        if v.as_tuple().exponent < -2:
            raise ValueError('El monto no puede tener más de 2 decimales')
        return v

    @validator('descripcion')
    def validate_descripcion(cls, v):
        """Validar descripción no vacía"""
        if not v or not v.strip():
            raise ValueError('La descripción es obligatoria')
        return v.strip()

    @validator('fecha_registro')
    def validate_fecha_registro(cls, v):
        """Validar que la fecha no sea futura"""
        from datetime import date
        if v > date.today():
            raise ValueError('La fecha de registro no puede ser futura')
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,  # Serializar Decimal como string para evitar problemas de precisión
        }


class CostoProyectoCreate(CostoProyectoBase):
    """Schema para crear nuevo costo de proyecto"""
    pass


class CostoProyectoUpdate(BaseModel):
    """Schema para actualizar costo de proyecto"""
    categoria: Optional[CategoriaCosto] = Field(None, description="Categoría del costo")
    descripcion: Optional[str] = Field(None, min_length=1, max_length=500, description="Descripción del costo")
    monto: Optional[Decimal] = Field(None, gt=0, description="Monto del costo")
    fecha_registro: Optional[date] = Field(None, description="Fecha del registro del costo")
    codigo_erp: Optional[str] = Field(None, max_length=50, description="Código de referencia del ERP")
    documento_referencia: Optional[str] = Field(None, max_length=100, description="Número de factura, guía, etc.")
    proveedor: Optional[str] = Field(None, max_length=200, description="Proveedor o empresa")

    @validator('monto')
    def validate_monto(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError('El monto debe ser mayor a 0')
            if v.as_tuple().exponent < -2:
                raise ValueError('El monto no puede tener más de 2 decimales')
        return v

    @validator('descripcion')
    def validate_descripcion(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('La descripción es obligatoria')
            return v.strip()
        return v

    @validator('fecha_registro')
    def validate_fecha_registro(cls, v):
        if v is not None:
            from datetime import date
            if v > date.today():
                raise ValueError('La fecha de registro no puede ser futura')
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
        }


class CostoProyectoResponse(CostoProyectoBase):
    """Schema para respuesta de costo de proyecto"""
    id: int
    created_at: Optional[str] = None  # Como string para compatibilidad frontend
    updated_at: Optional[str] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
        }


class ResumenCostosProyecto(BaseModel):
    """Schema para resumen de costos de un proyecto por categoría"""
    proyecto_id: int
    categoria: CategoriaCosto
    total_monto: Decimal
    cantidad_registros: int
    ultimo_registro: Optional[date] = None

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
        }


class CostoProyectoFilters(BaseModel):
    """Filtros para búsqueda de costos"""
    categoria: Optional[CategoriaCosto] = Field(None, description="Filtrar por categoría")
    fecha_desde: Optional[date] = Field(None, description="Fecha mínima de registro")
    fecha_hasta: Optional[date] = Field(None, description="Fecha máxima de registro")
    proveedor: Optional[str] = Field(None, max_length=200, description="Filtrar por proveedor")
    monto_minimo: Optional[Decimal] = Field(None, gt=0, description="Monto mínimo")
    monto_maximo: Optional[Decimal] = Field(None, gt=0, description="Monto máximo")

    @validator('fecha_hasta')
    def validate_fechas(cls, v, values):
        """Validar que fecha_hasta >= fecha_desde"""
        if v and values.get('fecha_desde') and v < values['fecha_desde']:
            raise ValueError('La fecha hasta debe ser mayor o igual a la fecha desde')
        return v

    @validator('monto_maximo')
    def validate_montos(cls, v, values):
        """Validar que monto_maximo >= monto_minimo"""
        if v and values.get('monto_minimo') and v < values['monto_minimo']:
            raise ValueError('El monto máximo debe ser mayor o igual al monto mínimo')
        return v

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
        }