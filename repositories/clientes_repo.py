from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import Cliente, User
from schemas.clientes import ClienteSearchFilters

class ClientesRepository:
    """Repository for Cliente operations"""
    
    @staticmethod
    def create(cliente_data: Dict[str, Any], created_by: str) -> Cliente:
        """Create a new cliente"""
        cliente = Cliente(**cliente_data)
        cliente.created_by = created_by
        db.session.add(cliente)
        db.session.flush()  # Get the ID without committing
        return cliente
    
    @staticmethod
    def get_by_id(cliente_id: int) -> Optional[Cliente]:
        """Get cliente by ID"""
        return db.session.get(Cliente, cliente_id)
    
    @staticmethod
    def get_by_rut(rut: str) -> Optional[Cliente]:
        """Get cliente by RUT"""
        return db.session.query(Cliente).filter_by(rut=rut).first()
    
    @staticmethod
    def update(cliente: Cliente, update_data: Dict[str, Any]) -> Cliente:
        """Update cliente"""
        for key, value in update_data.items():
            if hasattr(cliente, key) and value is not None:
                setattr(cliente, key, value)
        db.session.flush()
        return cliente
    
    @staticmethod
    def delete(cliente: Cliente) -> bool:
        """Soft delete cliente by setting activo to False"""
        cliente.activo = False
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: ClienteSearchFilters) -> tuple[List[Cliente], int]:
        """
        Search clientes with filters and pagination
        
        Returns:
            Tuple of (clientes_list, total_count)
        """
        query = db.session.query(Cliente).options(
            joinedload(Cliente.creator)
        )
        
        # Apply filters
        conditions = []
        
        if filters.nombre:
            conditions.append(Cliente.nombre.ilike(f"%{filters.nombre}%"))
        
        if filters.rut:
            clean_rut = filters.rut.replace('.', '').replace('-', '').strip()
            conditions.append(Cliente.rut.ilike(f"%{clean_rut}%"))
        
        if filters.contacto:
            conditions.append(or_(
                Cliente.contacto_principal.ilike(f"%{filters.contacto}%"),
                Cliente.email_contacto.ilike(f"%{filters.contacto}%")
            ))
        
        if filters.activo is not None:
            conditions.append(Cliente.activo == filters.activo)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        clientes = query.order_by(Cliente.nombre.asc()).offset(offset).limit(filters.per_page).all()
        
        return clientes, total_count
    
    @staticmethod
    def get_all_active() -> List[Cliente]:
        """Get all active clientes"""
        return db.session.query(Cliente).filter_by(activo=True).order_by(Cliente.nombre.asc()).all()
    
    @staticmethod
    def count_active() -> int:
        """Count active clientes"""
        return db.session.query(Cliente).filter_by(activo=True).count()
    
    @staticmethod
    def get_recent(limit: int = 10) -> List[Cliente]:
        """Get recently created clientes"""
        return (db.session.query(Cliente)
                .filter_by(activo=True)
                .order_by(Cliente.created_at.desc())
                .limit(limit)
                .all())
    
    @staticmethod
    def exists_rut(rut: str, exclude_id: int = None) -> bool:
        """Check if RUT already exists"""
        query = db.session.query(Cliente).filter_by(rut=rut)
        if exclude_id:
            query = query.filter(Cliente.id != exclude_id)
        return query.first() is not None
    
    @staticmethod
    def get_with_stats(cliente_id: int) -> Optional[Dict[str, Any]]:
        """Get cliente with related statistics"""
        cliente = ClientesRepository.get_by_id(cliente_id)
        if not cliente:
            return None
        
        # Get statistics
        from repositories.proyectos_repo import ProyectosRepository
        from repositories.contratos_repo import ContratosRepository
        
        stats = {
            'total_proyectos': len(cliente.proyectos),
            'proyectos_activos': ProyectosRepository.count_by_cliente_and_status(
                cliente_id, ['PENDIENTE_PRESUPUESTO', 'PRESUPUESTADO', 'ADJUDICADO', 'EN_DESARROLLO']
            ),
            'contratos_vigentes': ContratosRepository.count_by_cliente_and_status(
                cliente_id, 'VIGENTE'
            )
        }
        
        return {
            'cliente': cliente,
            'stats': stats
        }
