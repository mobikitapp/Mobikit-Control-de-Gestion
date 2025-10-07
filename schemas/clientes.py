from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class ClienteBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre del cliente")
    razon_social: Optional[str] = Field(None, max_length=250, description="Razón social del cliente")
    rut: str = Field(..., min_length=8, max_length=20, description="RUT del cliente")
    condiciones_comerciales: Optional[str] = Field(None, description="Condiciones comerciales")
    contacto_principal: Optional[str] = Field(None, max_length=200, description="Contacto principal")
    email_contacto: Optional[str] = Field(None, max_length=200, description="Email de contacto")
    telefono_contacto: Optional[str] = Field(None, max_length=50, description="Teléfono de contacto")
    direccion: Optional[str] = Field(None, description="Dirección del cliente")
    activo: bool = Field(True, description="Estado activo del cliente")

    @validator('rut')
    def validate_rut(cls, v):
        # Basic RUT validation - remove dots and hyphens
        clean_rut = v.replace('.', '').replace('-', '').strip().upper()
        if len(clean_rut) < 8 or not clean_rut[:-1].isdigit():
            raise ValueError('RUT inválido')
        return clean_rut

    @validator('email_contacto')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Email inválido')
        return v

class ClienteCreate(ClienteBase):
    pass

class ClienteUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    razon_social: Optional[str] = Field(None, max_length=250)
    rut: Optional[str] = Field(None, min_length=8, max_length=20)
    condiciones_comerciales: Optional[str] = None
    contacto_principal: Optional[str] = Field(None, max_length=200)
    email_contacto: Optional[str] = Field(None, max_length=200)
    telefono_contacto: Optional[str] = Field(None, max_length=50)
    direccion: Optional[str] = None
    activo: Optional[bool] = None

    @validator('rut')
    def validate_rut(cls, v):
        if v:
            clean_rut = v.replace('.', '').replace('-', '').strip().upper()
            if len(clean_rut) < 8 or not clean_rut[:-1].isdigit():
                raise ValueError('RUT inválido')
            return clean_rut
        return v

class ClienteResponse(ClienteBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True

class ClienteSearchFilters(BaseModel):
    nombre: Optional[str] = Field(None, description="Buscar por nombre")
    rut: Optional[str] = Field(None, description="Buscar por RUT")
    activo: Optional[bool] = Field(None, description="Filtrar por estado activo")
    contacto: Optional[str] = Field(None, description="Buscar por contacto")
    page: int = Field(1, ge=1, description="Número de página")
    per_page: int = Field(20, ge=1, le=100, description="Elementos por página")
