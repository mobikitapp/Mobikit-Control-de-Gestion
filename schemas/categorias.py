from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Enums para Pydantic
class CategoriaMuebleEnum(str, Enum):
    COCINA = "cocina"
    CLOSET = "closet"
    BANO = "bano"

class SubcategoriaCocinaEnum(str, Enum):
    BASES = "bases"
    MURALES = "murales"
    KITS = "kits"
    CUBIERTAS = "cubiertas"

class SubcategoriaClosetEnum(str, Enum):
    INTERIORES = "interiores"
    PIERNAS = "piernas"
    PUERTAS = "puertas"

# Esquemas base
class CategoriaBase(BaseModel):
    nombre: CategoriaMuebleEnum = Field(..., description="Nombre de la categoría")
    descripcion: Optional[str] = Field(None, max_length=200, description="Descripción de la categoría")
    activo: bool = Field(True, description="Estado activo de la categoría")

class CategoriaCreate(CategoriaBase):
    pass

class CategoriaUpdate(BaseModel):
    nombre: Optional[CategoriaMuebleEnum] = None
    descripcion: Optional[str] = Field(None, max_length=200)
    activo: Optional[bool] = None

class SubcategoriaBase(BaseModel):
    categoria_id: int = Field(..., description="ID de la categoría padre")
    nombre_cocina: Optional[SubcategoriaCocinaEnum] = Field(None, description="Nombre subcategoría cocina")
    nombre_closet: Optional[SubcategoriaClosetEnum] = Field(None, description="Nombre subcategoría closet")
    descripcion: Optional[str] = Field(None, max_length=200, description="Descripción de la subcategoría")
    activo: bool = Field(True, description="Estado activo de la subcategoría")

class SubcategoriaCreate(SubcategoriaBase):
    pass

class SubcategoriaUpdate(BaseModel):
    categoria_id: Optional[int] = None
    nombre_cocina: Optional[SubcategoriaCocinaEnum] = None
    nombre_closet: Optional[SubcategoriaClosetEnum] = None
    descripcion: Optional[str] = Field(None, max_length=200)
    activo: Optional[bool] = None

class SubcategoriaResponse(SubcategoriaBase):
    id: int
    created_at: datetime
    nombre_display: str = Field(..., description="Nombre para mostrar")

    class Config:
        from_attributes = True

class CategoriaResponse(CategoriaBase):
    id: int
    created_at: datetime
    subcategorias: List[SubcategoriaResponse] = []

    class Config:
        from_attributes = True

# Esquemas para tareas comerciales
class TareaComercialBase(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    vendedor_id: str = Field(..., description="ID del vendedor")
    titulo: str = Field(..., min_length=1, max_length=200, description="Título de la tarea")
    descripcion: Optional[str] = Field(None, description="Descripción detallada")
    fecha_limite: Optional[datetime] = Field(None, description="Fecha límite para completar")
    notas: Optional[str] = Field(None, description="Notas adicionales")

class TareaComercialCreate(TareaComercialBase):
    pass

class TareaComercialUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    completada: Optional[bool] = None
    fecha_limite: Optional[datetime] = None
    fecha_completada: Optional[datetime] = None
    notas: Optional[str] = None

class TareaComercialResponse(TareaComercialBase):
    id: int
    completada: bool
    fecha_completada: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    vendedor_nombre: Optional[str] = None
    proyecto_nombre: Optional[str] = None

    class Config:
        from_attributes = True

# Esquemas para asociación de categorías con proyectos/contratos
class ProyectoCategoriaAssign(BaseModel):
    categoria_ids: List[int] = Field(..., description="Lista de IDs de categorías")

class ContratoCategoriaAssign(BaseModel):
    categoria_ids: List[int] = Field(..., description="Lista de IDs de categorías")