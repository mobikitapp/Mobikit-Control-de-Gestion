from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from models import TipoBitacora

class BitacoraProyectoBase(BaseModel):
    comentario: str = Field(..., min_length=1, max_length=1000, description="Comentario de la bitácora")
    tipo: TipoBitacora = Field(TipoBitacora.GENERAL, description="Tipo de comentario")

class BitacoraProyectoCreate(BitacoraProyectoBase):
    proyecto_id: int = Field(..., description="ID del proyecto")

class BitacoraProyectoResponse(BitacoraProyectoBase):
    id: int
    proyecto_id: int
    usuario_id: str
    usuario_nombre: Optional[str] = None
    fecha_comentario: datetime

    class Config:
        from_attributes = True

class BitacoraProyectoFilters(BaseModel):
    proyecto_id: int = Field(..., description="ID del proyecto")
    tipo: Optional[TipoBitacora] = Field(None, description="Filtrar por tipo")
    usuario_id: Optional[str] = Field(None, description="Filtrar por usuario")
    limit: int = Field(50, ge=1, le=100, description="Límite de resultados")