from typing import List, Optional, Dict, Any
from app import db
from models import User, RolUsuario
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Service layer for User operations"""
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[User]:
        """Get user by ID"""
        return db.session.get(User, user_id)
    
    @staticmethod
    def get_active_users() -> List[User]:
        """Get all active users"""
        return (db.session.query(User)
                .filter_by(activo=True)
                .order_by(User.first_name, User.last_name)
                .all())
    
    @staticmethod
    def get_users_by_role(role: RolUsuario) -> List[User]:
        """Get users by specific role"""
        return (db.session.query(User)
                .filter_by(rol=role, activo=True)
                .order_by(User.first_name, User.last_name)
                .all())
    
    @staticmethod
    def get_production_users() -> List[User]:
        """Get users that can work in production areas"""
        return (db.session.query(User)
                .filter(User.rol.in_([
                    RolUsuario.ADMIN,
                    RolUsuario.OPERACIONES, 
                    RolUsuario.PRODUCCION
                ]))
                .filter_by(activo=True)
                .order_by(User.first_name, User.last_name)
                .all())
    
    @staticmethod
    def can_access_areas(user: User) -> bool:
        """Check if user can access areas functionality"""
        if not user or not user.activo:
            return False
        
        # All active users can view areas, but only certain roles can modify
        return user.rol in [
            RolUsuario.ADMIN,
            RolUsuario.OPERACIONES,
            RolUsuario.PRODUCCION,
            RolUsuario.LOGISTICA
        ]
    
    @staticmethod
    def can_modify_areas(user: User) -> bool:
        """Check if user can modify area states"""
        if not user or not user.activo:
            return False
        
        return user.rol in [
            RolUsuario.ADMIN,
            RolUsuario.OPERACIONES,
            RolUsuario.PRODUCCION
        ]
    
    @staticmethod
    def can_manage_dispatch(user: User) -> bool:
        """Check if user can manage dispatch operations"""
        if not user or not user.activo:
            return False
        
        return user.rol in [
            RolUsuario.ADMIN,
            RolUsuario.LOGISTICA
        ]
    
    @staticmethod
    def get_users_by_roles(roles: List[str]) -> List[User]:
        """Get users by multiple roles"""
        try:
            # Convert string roles to RolUsuario enums
            role_enums = []
            for role in roles:
                try:
                    role_enums.append(RolUsuario(role))
                except ValueError:
                    logger.warning(f"Invalid role: {role}")
                    continue
            
            if not role_enums:
                return []
            
            return (db.session.query(User)
                    .filter(User.rol.in_(role_enums))
                    .filter_by(activo=True)
                    .order_by(User.first_name, User.last_name)
                    .all())
        except Exception as e:
            logger.error(f"Error getting users by roles {roles}: {str(e)}")
            return []
from typing import List
from models import User
import logging

logger = logging.getLogger(__name__)

class UserService:
    """Service layer for User operations"""

    def get_active_users(self) -> List[User]:
        """Get all active users"""
        try:
            return User.query.filter_by(activo=True).all()
        except Exception as e:
            logger.error(f"Error getting active users: {str(e)}")
            raise
