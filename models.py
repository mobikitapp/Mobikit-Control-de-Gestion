from datetime import datetime
from enum import Enum
from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, Index
import pytz

# Timezone configuration
TIMEZONE = pytz.timezone('America/Santiago')

def utc_now():
    return datetime.now(pytz.UTC)

def local_now():
    return datetime.now(TIMEZONE)

# Enums for status fields
class EstadoProyecto(Enum):
    PLANIFICACION = "planificacion"
    EN_DESARROLLO = "en_desarrollo"
    PAUSADO = "pausado"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

class EstadoContrato(Enum):
    BORRADOR = "borrador"
    VIGENTE = "vigente"
    CERRADO = "cerrado"
    ANULADO = "anulado"

class EstadoOF(Enum):
    PLANIFICADA = "planificada"
    EN_PRODUCCION = "en_produccion"
    QA = "qa"
    TERMINADA = "terminada"
    ENTREGADA = "entregada"

class EstadoDespacho(Enum):
    PROGRAMADO = "programado"
    EN_TRANSPORTE = "en_transporte"
    ENTREGADO = "entregado"
    OBSERVADO = "observado"

class TipoAdjunto(Enum):
    CONTRATO = "contrato"
    PLANO = "plano"
    ESPECIFICACION = "especificacion"
    GUIA = "guia"
    ACTA = "acta"
    FOTO = "foto"
    QA = "qa"

class RolUsuario(Enum):
    ADMIN = "admin"
    OPERACIONES = "operaciones"
    VENTAS = "ventas"
    PRODUCCION = "produccion"
    LOGISTICA = "logistica"

# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=True)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    
    # Additional fields for the manufacturing app
    rol = db.Column(db.Enum(RolUsuario), default=RolUsuario.OPERACIONES, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f'<User {self.email}>'

    @property
    def nombre_completo(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email or self.id

# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)

class Cliente(db.Model):
    __tablename__ = 'clientes'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    rut = db.Column(db.String(20), unique=True, nullable=False)
    condiciones_comerciales = db.Column(db.Text)
    contacto_principal = db.Column(db.String(200))
    email_contacto = db.Column(db.String(200))
    telefono_contacto = db.Column(db.String(50))
    direccion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    proyectos = db.relationship('Proyecto', backref='cliente', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_cliente_rut', 'rut'),
        Index('idx_cliente_nombre', 'nombre'),
        Index('idx_cliente_activo', 'activo'),
    )

    def __repr__(self):
        return f'<Cliente {self.nombre}>'

class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Enum(EstadoProyecto), default=EstadoProyecto.PLANIFICACION, nullable=False)
    fecha_inicio = db.Column(db.Date)
    fecha_fin_estimada = db.Column(db.Date)
    fecha_fin_real = db.Column(db.Date)
    responsable = db.Column(db.String, db.ForeignKey('users.id'))
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    contratos = db.relationship('Contrato', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    ordenes_fabricacion = db.relationship('OrdenFabricacion', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    despachos = db.relationship('Despacho', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_proyecto_cliente', 'cliente_id'),
        Index('idx_proyecto_estado', 'estado'),
        Index('idx_proyecto_responsable', 'responsable'),
        Index('idx_proyecto_fechas', 'fecha_inicio', 'fecha_fin_estimada'),
    )

    def __repr__(self):
        return f'<Proyecto {self.nombre}>'

class Contrato(db.Model):
    __tablename__ = 'contratos'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    numero_oc = db.Column(db.String(50), unique=True, nullable=False)
    monto_total = db.Column(db.Numeric(15, 2))
    moneda = db.Column(db.String(3), default='CLP', nullable=False)
    estado = db.Column(db.Enum(EstadoContrato), default=EstadoContrato.BORRADOR, nullable=False)
    fecha_emision = db.Column(db.Date)
    fecha_vencimiento = db.Column(db.Date)
    condiciones_pago = db.Column(db.Text)
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    adjuntos = db.relationship('ContratoAdjunto', backref='contrato', lazy=True, cascade='all, delete-orphan')
    ordenes_fabricacion = db.relationship('OrdenFabricacion', backref='contrato', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_contrato_proyecto', 'proyecto_id'),
        Index('idx_contrato_numero_oc', 'numero_oc'),
        Index('idx_contrato_estado', 'estado'),
        Index('idx_contrato_fechas', 'fecha_emision', 'fecha_vencimiento'),
    )

    def __repr__(self):
        return f'<Contrato {self.numero_oc}>'

class ContratoAdjunto(db.Model):
    __tablename__ = 'contrato_adjuntos'
    
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.Enum(TipoAdjunto), default=TipoAdjunto.CONTRATO, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_contrato_adjunto_contrato', 'contrato_id'),
        Index('idx_contrato_adjunto_tipo', 'tipo'),
    )

    def __repr__(self):
        return f'<ContratoAdjunto {self.filename}>'

class OrdenFabricacion(db.Model):
    __tablename__ = 'ordenes_fabricacion'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Enum(EstadoOF), default=EstadoOF.PLANIFICADA, nullable=False)
    fecha_planificada = db.Column(db.Date)
    fecha_inicio = db.Column(db.DateTime)
    fecha_qc = db.Column(db.DateTime)
    fecha_fin = db.Column(db.DateTime)
    responsable = db.Column(db.String, db.ForeignKey('users.id'))
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    items = db.relationship('OrdenFabricacionItem', backref='orden_fabricacion', lazy=True, cascade='all, delete-orphan')
    despachos = db.relationship('Despacho', backref='orden_fabricacion', lazy=True)
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_of_proyecto', 'proyecto_id'),
        Index('idx_of_contrato', 'contrato_id'),
        Index('idx_of_codigo', 'codigo'),
        Index('idx_of_estado', 'estado'),
        Index('idx_of_responsable', 'responsable'),
        Index('idx_of_fechas', 'fecha_planificada', 'fecha_inicio'),
    )

    def __repr__(self):
        return f'<OrdenFabricacion {self.codigo}>'

class OrdenFabricacionItem(db.Model):
    __tablename__ = 'of_items'
    
    id = db.Column(db.Integer, primary_key=True)
    of_id = db.Column(db.Integer, db.ForeignKey('ordenes_fabricacion.id'), nullable=False)
    sku_codigo = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)
    unidad = db.Column(db.String(20), default='UN', nullable=False)
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    
    # Indexes
    __table_args__ = (
        Index('idx_of_item_of', 'of_id'),
        Index('idx_of_item_sku', 'sku_codigo'),
    )

    def __repr__(self):
        return f'<OrdenFabricacionItem {self.sku_codigo}>'

class Despacho(db.Model):
    __tablename__ = 'despachos'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    of_id = db.Column(db.Integer, db.ForeignKey('ordenes_fabricacion.id'), nullable=True)
    numero_despacho = db.Column(db.String(50), unique=True, nullable=False)
    estado = db.Column(db.Enum(EstadoDespacho), default=EstadoDespacho.PROGRAMADO, nullable=False)
    fecha_programada = db.Column(db.Date)
    fecha_envio = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    destino = db.Column(db.Text, nullable=False)
    contacto_destino = db.Column(db.String(200))
    telefono_contacto = db.Column(db.String(50))
    observaciones = db.Column(db.Text)
    responsable = db.Column(db.String, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    adjuntos = db.relationship('DespachoAdjunto', backref='despacho', lazy=True, cascade='all, delete-orphan')
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_despacho_proyecto', 'proyecto_id'),
        Index('idx_despacho_of', 'of_id'),
        Index('idx_despacho_numero', 'numero_despacho'),
        Index('idx_despacho_estado', 'estado'),
        Index('idx_despacho_responsable', 'responsable'),
        Index('idx_despacho_fechas', 'fecha_programada', 'fecha_envio'),
    )

    def __repr__(self):
        return f'<Despacho {self.numero_despacho}>'

class DespachoAdjunto(db.Model):
    __tablename__ = 'despacho_adjuntos'
    
    id = db.Column(db.Integer, primary_key=True)
    despacho_id = db.Column(db.Integer, db.ForeignKey('despachos.id'), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.Enum(TipoAdjunto), nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_despacho_adjunto_despacho', 'despacho_id'),
        Index('idx_despacho_adjunto_tipo', 'tipo'),
    )

    def __repr__(self):
        return f'<DespachoAdjunto {self.filename}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    entidad = db.Column(db.String(50), nullable=False)  # nombre de la tabla/modelo
    entidad_id = db.Column(db.Integer, nullable=False)  # ID del registro afectado
    accion = db.Column(db.String(20), nullable=False)   # CREATE, UPDATE, DELETE
    actor = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    payload = db.Column(db.JSON)  # datos del cambio
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    
    # Relationships
    actor_user = db.relationship('User', foreign_keys=[actor])
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_entidad', 'entidad', 'entidad_id'),
        Index('idx_audit_actor', 'actor'),
        Index('idx_audit_created', 'created_at'),
    )

    def __repr__(self):
        return f'<AuditLog {self.entidad}:{self.entidad_id} {self.accion}>'
