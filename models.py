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
    PLANIFICACION = "PLANIFICACION"
    EN_DESARROLLO = "EN_DESARROLLO"
    PAUSADO = "PAUSADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"

class TipoDocumento(Enum):
    CONTRATO = "contrato"
    ORDEN_COMPRA = "orden_compra"

class EstadoContrato(Enum):
    BORRADOR = "BORRADOR"
    VIGENTE = "VIGENTE"
    CERRADO = "CERRADO"
    ANULADO = "ANULADO"

class EstadoOF(Enum):
    PLANIFICADA = "PLANIFICADA"
    ENVIADO_PRODUCCION = "ENVIADO_PRODUCCION"
    SECCIONANDO = "SECCIONANDO"
    EN_PRODUCCION = "EN_PRODUCCION"
    QA = "QA"
    TERMINADA = "TERMINADA"
    ENTREGADA = "ENTREGADA"

class EstadoDespacho(Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ENTREGADO = "ENTREGADO"
    OBSERVADO = "OBSERVADO"

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

class EstadoComercial(Enum):
    PENDIENTE_PRESUPUESTO = "PENDIENTE_PRESUPUESTO"
    PRESUPUESTADO = "PRESUPUESTADO"
    ADJUDICADO = "ADJUDICADO"
    TERMINADO = "TERMINADO"

# Enums para eventos de calendario
class TipoEvento(Enum):
    ENTREGA = "entrega"

class EstadoEvento(Enum):
    PENDIENTE = "pendiente"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

class PrioridadEvento(Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"

# Enums para el sistema de áreas
class TipoArea(Enum):
    PENDIENTES_FABRICACION = "pendientes_fabricacion"
    FABRICA = "fabrica"
    EMBALAJE = "embalaje"
    BODEGA = "bodega"
    DESPACHO = "despacho"

class EstadoPendientesFabricacion(Enum):
    PENDIENTE_APROBACION_DISENO = "pendiente_aprobacion_diseño"
    APROBADO = "aprobado"

class EstadoFabrica(Enum):
    ENVIADO_A_FABRICACION = "enviado_a_fabricacion"
    SECCIONANDO = "seccionando"
    ENCHAPANDO = "enchapando"
    MECANIZANDO = "mecanizando"
    FABRICACION_COMPLETA = "fabricacion_completa"

class EstadoEmbalaje(Enum):
    PENDIENTE_DE_EMBALAR = "pendiente_de_embalar"
    EMBALANDO = "embalando"
    EMBALAJE_LISTO = "embalaje_listo"

class EstadoBodega(Enum):
    LISTO_PARA_DESPACHO = "listo_para_despacho"

class EstadoDespachoArea(Enum):
    DESPACHADO = "despachado"

# Enums para categorización de muebles
class CategoriaMueble(Enum):
    COCINA = "cocina"
    CLOSET = "closet"
    BANO = "bano"

class SubcategoriaCocina(Enum):
    BASES = "bases"
    MURALES = "murales"
    KITS = "kits"
    CUBIERTAS = "cubiertas"

class SubcategoriaCloset(Enum):
    INTERIORES = "interiores"
    PIERNAS = "piernas"
    PUERTAS = "puertas"

# Baño no tiene subcategorías


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
    
    # Campos comerciales
    vendedor_id = db.Column(db.String, db.ForeignKey('users.id'))
    estado_comercial = db.Column(db.Enum(EstadoComercial), default=EstadoComercial.PENDIENTE_PRESUPUESTO)
    monto_provision_presupuestado = db.Column(db.Numeric(15, 2))
    margen_venta_provision = db.Column(db.Numeric(5, 2))  # Porcentaje
    monto_instalacion_presupuestado = db.Column(db.Numeric(15, 2))
    margen_venta_instalacion = db.Column(db.Numeric(5, 2))  # Porcentaje
    fecha_presupuesto = db.Column(db.Date)
    fecha_adjudicacion = db.Column(db.Date)
    notas_comerciales = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    contratos = db.relationship('Contrato', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    ordenes_fabricacion = db.relationship('OrdenFabricacion', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    despachos = db.relationship('Despacho', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    eventos_entrega = db.relationship('EventoEntrega', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    vendedor_user = db.relationship('User', foreign_keys=[vendedor_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    tareas_comerciales = db.relationship('TareaComercial', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_proyecto_cliente', 'cliente_id'),
        Index('idx_proyecto_estado', 'estado'),
        Index('idx_proyecto_responsable', 'responsable'),
        Index('idx_proyecto_fechas', 'fecha_inicio', 'fecha_fin_estimada'),
    )

    def __repr__(self):
        return f'<Proyecto {self.nombre}>'

# Tablas de asociación para relaciones many-to-many
proyecto_categorias = db.Table('proyecto_categorias',
    db.Column('proyecto_id', db.Integer, db.ForeignKey('proyectos.id'), primary_key=True),
    db.Column('categoria_id', db.Integer, db.ForeignKey('categorias_mueble.id'), primary_key=True)
)

contrato_categorias = db.Table('contrato_categorias',
    db.Column('contrato_id', db.Integer, db.ForeignKey('contratos.id'), primary_key=True),
    db.Column('categoria_id', db.Integer, db.ForeignKey('categorias_mueble.id'), primary_key=True)
)

class CategoriaMuebleModel(db.Model):
    __tablename__ = 'categorias_mueble'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.Enum(CategoriaMueble), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    
    # Relationships
    subcategorias = db.relationship('SubcategoriaMuebleModel', backref='categoria', lazy=True, cascade='all, delete-orphan')
    proyectos = db.relationship('Proyecto', secondary=proyecto_categorias, backref='categorias_mueble')
    contratos = db.relationship('Contrato', secondary=contrato_categorias, backref='categorias_mueble')
    
    def __repr__(self):
        return f'<CategoriaMueble {self.nombre.value}>'

class SubcategoriaMuebleModel(db.Model):
    __tablename__ = 'subcategorias_mueble'
    
    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias_mueble.id'), nullable=False)
    nombre_cocina = db.Column(db.Enum(SubcategoriaCocina), nullable=True)  # Solo para cocina
    nombre_closet = db.Column(db.Enum(SubcategoriaCloset), nullable=True)  # Solo para closet
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    
    # Índices
    __table_args__ = (
        Index('idx_subcategoria_categoria', 'categoria_id'),
    )
    
    def __repr__(self):
        nombre = self.nombre_cocina.value if self.nombre_cocina else (self.nombre_closet.value if self.nombre_closet else 'Sin nombre')
        return f'<SubcategoriaMueble {nombre}>'
    
    @property
    def nombre_display(self):
        if self.nombre_cocina:
            return self.nombre_cocina.value
        elif self.nombre_closet:
            return self.nombre_closet.value
        return 'Sin nombre'


class Contrato(db.Model):
    __tablename__ = 'contratos'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    tipo_documento = db.Column(db.Enum(TipoDocumento), default=TipoDocumento.CONTRATO, nullable=False)
    numero_oc = db.Column(db.String(50), unique=True, nullable=False)
    monto_total = db.Column(db.Numeric(15, 2))
    moneda = db.Column(db.String(3), default='CLP', nullable=False)
    estado = db.Column(db.Enum(EstadoContrato), default=EstadoContrato.BORRADOR, nullable=False)
    fecha_emision = db.Column(db.Date)
    fecha_vencimiento = db.Column(db.Date)
    fecha_entrega_comprometida = db.Column(db.Date)
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
        Index('idx_contrato_tipo', 'tipo_documento'),
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
    glosa = db.Column(db.Text)
    cantidad_tableros = db.Column(db.Integer)
    fecha_entrega_fabrica = db.Column(db.Date)
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

# Sistema de Áreas de Producción
class Area(db.Model):
    __tablename__ = 'areas'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Enum(TipoArea), nullable=False, unique=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    orden_secuencia = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    color_hex = db.Column(db.String(7), default='#6c757d')  # Color para UI
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    estados = db.relationship('AreaEstado', backref='area', lazy=True, cascade='all, delete-orphan')
    progresos = db.relationship('OrdenAreaProgreso', backref='area', lazy=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_area_tipo', 'tipo'),
        Index('idx_area_orden', 'orden_secuencia'),
        Index('idx_area_activo', 'activo'),
    )

    def __repr__(self):
        return f'<Area {self.nombre}>'

class AreaEstado(db.Model):
    __tablename__ = 'area_estados'
    
    id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    codigo = db.Column(db.String(50), nullable=False)  # código técnico del estado
    nombre = db.Column(db.String(100), nullable=False)  # nombre para mostrar
    descripcion = db.Column(db.Text)
    orden_en_area = db.Column(db.Integer, nullable=False)
    es_inicial = db.Column(db.Boolean, default=False, nullable=False)  # Estado por defecto al llegar al área
    es_final = db.Column(db.Boolean, default=False, nullable=False)    # Estado de salida del área
    activo = db.Column(db.Boolean, default=True, nullable=False)
    color_hex = db.Column(db.String(7), default='#6c757d')
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    progresos = db.relationship('OrdenAreaProgreso', backref='estado', lazy=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_area_estado_area', 'area_id'),
        Index('idx_area_estado_codigo', 'area_id', 'codigo'),
        Index('idx_area_estado_orden', 'area_id', 'orden_en_area'),
        Index('idx_area_estado_inicial', 'area_id', 'es_inicial'),
        Index('idx_area_estado_final', 'area_id', 'es_final'),
    )

    def __repr__(self):
        return f'<AreaEstado {self.area.nombre}:{self.nombre}>'

class OrdenAreaProgreso(db.Model):
    __tablename__ = 'orden_area_progreso'
    
    id = db.Column(db.Integer, primary_key=True)
    orden_fabricacion_id = db.Column(db.Integer, db.ForeignKey('ordenes_fabricacion.id'), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    estado_id = db.Column(db.Integer, db.ForeignKey('area_estados.id'), nullable=False)
    
    # Timestamps
    fecha_ingreso_area = db.Column(db.DateTime, nullable=False)  # Cuándo llegó a esta área
    fecha_cambio_estado = db.Column(db.DateTime, nullable=False) # Cuándo cambió al estado actual
    
    # Asignación y seguimiento
    responsable_area = db.Column(db.String, db.ForeignKey('users.id'))  # Usuario responsable en esta área
    tiempo_estimado_horas = db.Column(db.Numeric(10, 2))  # Tiempo estimado para completar en esta área
    notas_area = db.Column(db.Text)  # Observaciones específicas del área
    
    # Control de flujo
    es_actual = db.Column(db.Boolean, default=True, nullable=False)  # Si es el progreso activo (para historial)
    archivado = db.Column(db.Boolean, default=False, nullable=False)  # Para despachos archivados
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    orden_fabricacion = db.relationship('OrdenFabricacion', backref='area_progresos')
    responsable_user = db.relationship('User', foreign_keys=[responsable_area])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_progreso_orden', 'orden_fabricacion_id'),
        Index('idx_progreso_area', 'area_id'),
        Index('idx_progreso_estado', 'estado_id'),
        Index('idx_progreso_actual', 'orden_fabricacion_id', 'es_actual'),
        Index('idx_progreso_responsable', 'responsable_area'),
        Index('idx_progreso_archivado', 'archivado'),
        Index('idx_progreso_fechas', 'fecha_ingreso_area', 'fecha_cambio_estado'),
    )

    def __repr__(self):
        return f'<OrdenAreaProgreso OF:{self.orden_fabricacion_id} {self.area.nombre}:{self.estado.nombre}>'

class ContratoEntrega(db.Model):
    __tablename__ = 'contrato_entregas'
    
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    fecha_entrega = db.Column(db.Date, nullable=False)
    glosa_entrega = db.Column(db.String(500), nullable=False)  # Descripción de qué se entrega
    monto_parcial = db.Column(db.Numeric(15, 2))  # Monto de esta entrega parcial
    orden_entrega = db.Column(db.Integer, nullable=False)  # Orden secuencial de entrega
    completada = db.Column(db.Boolean, default=False, nullable=False)
    fecha_completada = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    contrato = db.relationship('Contrato', backref='entregas')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_entrega_contrato', 'contrato_id'),
        Index('idx_entrega_fecha', 'fecha_entrega'),
        Index('idx_entrega_orden', 'contrato_id', 'orden_entrega'),
        Index('idx_entrega_completada', 'completada'),
    )

    def __repr__(self):
        return f'<ContratoEntrega {self.contrato.numero_oc}:{self.orden_entrega}>'


# Modelos para área comercial

class TareaComercial(db.Model):
    __tablename__ = 'tareas_comerciales'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    vendedor_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    completada = db.Column(db.Boolean, default=False, nullable=False)
    fecha_limite = db.Column(db.Date)
    fecha_completada = db.Column(db.DateTime)
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    vendedor = db.relationship('User', foreign_keys=[vendedor_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_tarea_proyecto', 'proyecto_id'),
        Index('idx_tarea_vendedor', 'vendedor_id'),
        Index('idx_tarea_estado', 'completada'),
    )

    def __repr__(self):
        return f'<TareaComercial {self.titulo}>'


class ObjetivoMensual(db.Model):
    __tablename__ = 'objetivos_mensuales'
    
    id = db.Column(db.Integer, primary_key=True)
    año = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)  # 1-12
    objetivo_provision = db.Column(db.Numeric(15, 2))
    objetivo_instalacion = db.Column(db.Numeric(15, 2))
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('año', 'mes', name='uq_objetivo_año_mes'),
        Index('idx_objetivo_periodo', 'año', 'mes'),
    )

    def __repr__(self):
        return f'<ObjetivoMensual {self.año}-{self.mes:02d}>'


# Modelos para calendario de eventos

class EventoEntrega(db.Model):
    __tablename__ = 'eventos_entrega'
    
    id = db.Column(db.String, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'))
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'))
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    fecha_evento = db.Column(db.Date, nullable=False)
    hora_evento = db.Column(db.Time)
    tipo_evento = db.Column(db.Enum(TipoEvento), nullable=False)
    estado = db.Column(db.Enum(EstadoEvento), default=EstadoEvento.PENDIENTE, nullable=False)
    prioridad = db.Column(db.Enum(PrioridadEvento), default=PrioridadEvento.MEDIA, nullable=False)
    
    # Recordatorio
    recordatorio_dias = db.Column(db.Integer, default=1)  # Días antes del evento para recordatorio
    recordatorio_enviado = db.Column(db.Boolean, default=False, nullable=False)
    
    # Seguimiento
    fecha_completado = db.Column(db.DateTime)
    completado_por = db.Column(db.String, db.ForeignKey('users.id'))
    notas = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    contrato = db.relationship('Contrato', backref='eventos_entrega')
    completado_por_user = db.relationship('User', foreign_keys=[completado_por])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_evento_proyecto', 'proyecto_id'),
        Index('idx_evento_fecha', 'fecha_evento'),
        Index('idx_evento_estado', 'estado'),
        Index('idx_evento_tipo', 'tipo_evento'),
        Index('idx_evento_recordatorio', 'fecha_evento', 'recordatorio_dias', 'recordatorio_enviado'),
    )

    def __repr__(self):
        return f'<EventoEntrega {self.titulo}>'
    
    @property 
    def fecha_recordatorio(self):
        """Fecha en que debe enviarse el recordatorio"""
        if self.recordatorio_dias and self.fecha_evento:
            from datetime import timedelta
            return self.fecha_evento - timedelta(days=self.recordatorio_dias)
        return None
