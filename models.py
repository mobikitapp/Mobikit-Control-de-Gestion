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

class TipoDocumento(Enum):
    CONTRATO = "CONTRATO"
    ORDEN_COMPRA = "ORDEN_COMPRA"

class EstadoContrato(Enum):
    BORRADOR = "BORRADOR"
    VIGENTE = "VIGENTE"
    CERRADO = "CERRADO"
    ANULADO = "ANULADO"

class EstadoOF(Enum):
    # Estados de Pendientes de Fabricación - sincronizados con BD
    PENDIENTE_APROBACION_DISENO = "pendiente_aprobacion_diseño"
    APROBADO = "aprobado"
    # Estados de Fábrica - sincronizados con BD
    ENVIADO_A_FABRICACION = "enviado_a_fabricacion"
    SECCIONANDO = "seccionando"
    ENCHAPANDO = "enchapando"
    MECANIZANDO = "mecanizando"
    FABRICACION_COMPLETA = "fabricacion_completa"
    # Estados de Embalaje - sincronizados con BD
    PENDIENTE_DE_EMBALAR = "pendiente_de_embalar"
    EMBALANDO = "embalando"
    EMBALAJE_LISTO = "embalaje_listo"
    # Estados de Bodega - sincronizados con BD
    LISTO_PARA_DESPACHO = "listo_para_despacho"
    PROGRAMADO_PARA_DESPACHO = "programado_para_despacho"
    # Estados de Despacho - sincronizados con BD
    DESPACHADO = "despachado"

class EstadoDespacho(Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ENTREGADO = "ENTREGADO"
    OBSERVADO = "OBSERVADO"

class TipoEstadoPago(Enum):
    PENDIENTE_FACTURAR = "PENDIENTE_FACTURAR"
    FACTURADO = "FACTURADO"
    PAGADO = "PAGADO"
    ANULADO = "ANULADO"


class TipoAdjunto(Enum):
    CONTRATO = "contrato"
    PLANO = "plano"
    ESPECIFICACION = "especificacion"
    PRESUPUESTO = "presupuesto"
    EETT = "eett"
    GUIA = "guia"
    ACTA = "acta"
    FOTO = "foto"
    QA = "qa"

class TipoBitacora(Enum):
    ESPECIFICACION = "especificacion"
    CAMBIO = "cambio"
    NOTA = "nota"
    GENERAL = "general"

class TipoNotificacion(Enum):
    NUEVO_PROYECTO = 'nuevo_proyecto'
    COMENTARIO_BITACORA = 'comentario_bitacora'
    CAMBIO_ESTADO_OF = 'cambio_estado_of'
    VENCIMIENTO_CONTRATO = 'vencimiento_contrato'
    RETRASO_PROYECTO = 'retraso_proyecto'

class RolUsuario(Enum):
    ADMIN = "admin"
    GENERAL = "general"
    OPERACIONES = "operaciones"
    VENTAS = "ventas"
    PRODUCCION = "produccion"
    LOGISTICA = "logistica"
    FINANZAS = "finanzas"

class EstadoComercial(Enum):
    PENDIENTE_PRESUPUESTO = "PENDIENTE_PRESUPUESTO"
    PRESUPUESTADO = "PRESUPUESTADO"
    ADJUDICADO = "ADJUDICADO"
    EN_DESARROLLO = "EN_DESARROLLO"
    TERMINADO = "TERMINADO"

class TipoProyecto(Enum):
    SOCIAL = "SOCIAL"
    ESTANDAR = "ESTANDAR"
    ESPECIAL = "ESPECIAL"

class TipoVivienda(Enum):
    CASA = "CASA"
    DEPARTAMENTO = "DEPARTAMENTO"

# Enums para eventos de calendario
class TipoEvento(Enum):
    ENTREGA = "entrega"

class EstadoEvento(Enum):
    PENDIENTE = "pendiente"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

class PrioridadOrden(Enum):
    # Formato tradicional
    BAJA = "baja"
    MEDIA = "media" 
    ALTA = "alta"
    URGENTE = "urgente"
    # Formato numérico
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

    @classmethod
    def get_orden_valor(cls, prioridad):
        """Obtiene el valor numérico para ordenamiento (menor = mayor prioridad)"""
        orden_map = {
            cls.P1: 1, cls.URGENTE: 1,
            cls.P2: 2, cls.ALTA: 2,
            cls.P3: 3, cls.MEDIA: 3,
            cls.P4: 4, cls.BAJA: 4
        }
        return orden_map.get(prioridad, 99)

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
    # Sincronizado con EstadoOF y BD
    PENDIENTE_APROBACION_DISENO = "pendiente_aprobacion_diseño"
    APROBADO = "aprobado"

class EstadoFabrica(Enum):
    # Sincronizado con EstadoOF y BD
    ENVIADO_A_FABRICACION = "enviado_a_fabricacion"
    SECCIONANDO = "seccionando"
    ENCHAPANDO = "enchapando"
    MECANIZANDO = "mecanizando"
    FABRICACION_COMPLETA = "fabricacion_completa"

class EstadoEmbalaje(Enum):
    # Sincronizado con EstadoOF y BD
    PENDIENTE_DE_EMBALAR = "pendiente_de_embalar"
    EMBALANDO = "embalando"
    EMBALAJE_LISTO = "embalaje_listo"

class EstadoBodega(Enum):
    # Sincronizado con EstadoOF y BD
    LISTO_PARA_DESPACHO = "listo_para_despacho"
    PROGRAMADO_PARA_DESPACHO = "programado_para_despacho"

class EstadoDespachoArea(Enum):
    # Sincronizado con EstadoOF y BD
    DESPACHADO = "despachado"

# Enums para despachos parciales

# Enum para tipos de permisos
class TipoPermiso(Enum):
    LECTURA = "lectura"
    CREACION = "creacion"
    EDICION = "edicion"
    ELIMINACION = "eliminacion"
class TipoDespacho(Enum):
    TOTAL = "TOTAL"
    PARCIAL = "PARCIAL"

class EstadoDespachoBodega(Enum):
    LISTO_PARA_DESPACHO = "listo_para_despacho"
    PARCIALMENTE_DESPACHADO = "parcialmente_despachado" 
    COMPLETAMENTE_DESPACHADO = "completamente_despachado"


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

class EstadoHitoEntrega(Enum):
    PENDIENTE = "pendiente"
    COMPLETADO = "completado"
    ATRASADO = "atrasado"

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
    fecha_inicio = db.Column(db.Date)
    fecha_fin_estimada = db.Column(db.Date)
    fecha_fin_real = db.Column(db.Date)
    responsable = db.Column(db.String, db.ForeignKey('users.id'))
    notas = db.Column(db.Text)

    # Campos comerciales
    vendedor_id = db.Column(db.String, db.ForeignKey('users.id'))
    estado_comercial = db.Column(db.Enum(EstadoComercial), default=EstadoComercial.PENDIENTE_PRESUPUESTO)
    monto_provision_presupuestado = db.Column(db.Numeric(15, 2))  # Monto neto de venta por provisión
    margen_venta_provision = db.Column(db.Numeric(5, 2))  # Porcentaje de ganancia sobre provisión
    monto_instalacion_presupuestado = db.Column(db.Numeric(15, 2))  # Monto neto de venta por instalación
    margen_venta_instalacion = db.Column(db.Numeric(5, 2))  # Porcentaje de ganancia sobre instalación
    
    # Campos para soporte de UF en presupuestos
    monto_provision_presupuestado_uf = db.Column(db.Numeric(15, 4))  # Monto provisión en UF
    monto_instalacion_presupuestado_uf = db.Column(db.Numeric(15, 4))  # Monto instalación en UF
    valor_uf_presupuesto = db.Column(db.Numeric(15, 2))  # Valor UF usado en presupuesto
    fecha_conversion_presupuesto_uf = db.Column(db.Date)  # Fecha conversión presupuesto
    moneda_original_presupuesto = db.Column(db.String(3))  # Moneda original ('UF' o 'CLP')
    
    fecha_presupuesto = db.Column(db.Date)
    fecha_adjudicacion = db.Column(db.Date)
    notas_comerciales = db.Column(db.Text)

    # Campos adicionales opcionales para vendedores
    tipo_proyecto = db.Column(db.Enum(TipoProyecto), default=TipoProyecto.ESTANDAR)  # Social, Estándar, Especial
    tipo_vivienda = db.Column(db.Enum(TipoVivienda))  # Casa, Departamento
    numero_viviendas = db.Column(db.Integer)  # Número de viviendas
    ubicacion_obra = db.Column(db.String(500))  # Ubicación de la obra (se relaciona con direcciones de despacho)
    
    # Campo para integración con ERP Mobikit
    centro_costo = db.Column(db.Integer)  # Centro de costo para enlace con ERP

    activo = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    contratos = db.relationship('Contrato', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    ordenes_fabricacion = db.relationship('OrdenFabricacion', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    despachos = db.relationship('Despacho', backref='proyecto', lazy=True, cascade='all, delete-orphan')
    eventos_entrega = db.relationship('EventoEntrega', foreign_keys='EventoEntrega.proyecto_id', lazy=True, cascade='all, delete-orphan')
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    vendedor_user = db.relationship('User', foreign_keys=[vendedor_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    tareas_comerciales = db.relationship('TareaComercial', backref='proyecto', lazy=True, cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_proyecto_cliente', 'cliente_id'),
        Index('idx_proyecto_estado_comercial', 'estado_comercial'),
        Index('idx_proyecto_responsable', 'responsable'),
        Index('idx_proyecto_fechas', 'fecha_inicio', 'fecha_fin_estimada'),
    )

    def __repr__(self):
        return f'<Proyecto {self.nombre}>'
    
    @property
    def presupuesto_actualizado_uf(self):
        """Obtiene presupuestos actualizados según UF actual si fueron ingresados en UF"""
        from services.uf_conversion_service import UfConversionService
        from decimal import Decimal
        
        result = {
            'provision': {
                'monto_clp': self.monto_provision_presupuestado,
                'fue_ingresado_en_uf': self.moneda_original_presupuesto == 'UF'
            },
            'instalacion': {
                'monto_clp': self.monto_instalacion_presupuestado,
                'fue_ingresado_en_uf': self.moneda_original_presupuesto == 'UF'
            }
        }
        
        # Actualizar provisión si fue ingresada en UF
        if (self.moneda_original_presupuesto == 'UF' and 
            self.monto_provision_presupuestado_uf):
            conversion = UfConversionService.convert_uf_to_clp(
                Decimal(str(self.monto_provision_presupuestado_uf))
            )
            if conversion:
                result['provision']['monto_clp_actualizado'] = conversion['clp_amount']
                result['provision']['monto_uf_original'] = self.monto_provision_presupuestado_uf
        
        # Actualizar instalación si fue ingresada en UF
        if (self.moneda_original_presupuesto == 'UF' and 
            self.monto_instalacion_presupuestado_uf):
            conversion = UfConversionService.convert_uf_to_clp(
                Decimal(str(self.monto_instalacion_presupuestado_uf))
            )
            if conversion:
                result['instalacion']['monto_clp_actualizado'] = conversion['clp_amount']
                result['instalacion']['monto_uf_original'] = self.monto_instalacion_presupuestado_uf
        
        # Agregar información de conversión
        result['valor_uf_presupuesto'] = self.valor_uf_presupuesto
        result['fecha_conversion'] = self.fecha_conversion_presupuesto_uf
        
        return result
    
    @property
    def monto_total_presupuestado(self):
        """Calcula el monto total presupuestado (provisión + instalación)"""
        provision = self.monto_provision_presupuestado or 0
        instalacion = self.monto_instalacion_presupuestado or 0
        return provision + instalacion
    
    @property
    def monto_total_presupuestado_actualizado(self):
        """Monto total presupuestado con valores UF actualizados"""
        presupuesto = self.presupuesto_actualizado_uf
        
        provision = (presupuesto['provision'].get('monto_clp_actualizado') or 
                    presupuesto['provision']['monto_clp'] or 0)
        instalacion = (presupuesto['instalacion'].get('monto_clp_actualizado') or 
                      presupuesto['instalacion']['monto_clp'] or 0)
        
        return provision + instalacion

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
    
    # Campos para soporte de UF
    monto_total_uf = db.Column(db.Numeric(15, 4))  # Monto original en UF (mayor precisión)
    valor_uf_conversion = db.Column(db.Numeric(15, 2))  # Valor UF usado para conversión
    fecha_conversion_uf = db.Column(db.Date)  # Fecha de conversión UF a CLP
    moneda_original = db.Column(db.String(3))  # Moneda original de entrada ('UF' o 'CLP')
    
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
    plan_entrega = db.relationship('PlanEntrega', backref='contrato', uselist=False, cascade='all, delete-orphan')
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
    
    @property
    def monto_total_actualizado(self):
        """Obtiene el monto total actualizado según UF actual si fue ingresado en UF"""
        if self.moneda_original == 'UF' and self.monto_total_uf:
            from services.uf_conversion_service import UfConversionService
            from decimal import Decimal
            
            conversion = UfConversionService.convert_uf_to_clp(Decimal(str(self.monto_total_uf)))
            if conversion:
                return conversion['clp_amount']
        
        return self.monto_total
    
    @property
    def monto_display_info(self):
        """Información completa para mostrar el monto con contexto UF"""
        info = {
            'monto_clp': self.monto_total,
            'moneda': self.moneda,
            'fue_ingresado_en_uf': self.moneda_original == 'UF',
            'monto_uf_original': self.monto_total_uf,
            'valor_uf_conversion': self.valor_uf_conversion,
            'fecha_conversion': self.fecha_conversion_uf
        }
        
        if self.moneda_original == 'UF':
            info['monto_clp_actualizado'] = self.monto_total_actualizado
        
        return info


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

class PlanEntrega(db.Model):
    __tablename__ = 'planes_entrega'

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False, unique=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    hitos = db.relationship('HitoEntrega', backref='plan_entrega', lazy=True, cascade='all, delete-orphan', order_by='HitoEntrega.fecha_programada')
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_plan_entrega_contrato', 'contrato_id'),
    )

    def __repr__(self):
        return f'<PlanEntrega {self.nombre}>'

class HitoEntrega(db.Model):
    __tablename__ = 'hitos_entrega'

    id = db.Column(db.Integer, primary_key=True)
    plan_entrega_id = db.Column(db.Integer, db.ForeignKey('planes_entrega.id'), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=1)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    fecha_programada = db.Column(db.Date, nullable=False)
    fecha_completado = db.Column(db.DateTime)
    estado = db.Column(db.Enum(EstadoHitoEntrega), default=EstadoHitoEntrega.PENDIENTE, nullable=False)
    notas_completado = db.Column(db.Text)
    completado_por = db.Column(db.String, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    completado_por_user = db.relationship('User', foreign_keys=[completado_por])
    evento_entrega = db.relationship('EventoEntrega', backref='hito', uselist=False)
    despachos = db.relationship('Despacho', foreign_keys='Despacho.hito_entrega_id', overlaps="despachos_hito,hito_entrega", lazy=True)

    # Indexes
    __table_args__ = (
        Index('idx_hito_entrega_plan', 'plan_entrega_id'),
        Index('idx_hito_entrega_fecha', 'fecha_programada'),
        Index('idx_hito_entrega_estado', 'estado'),
        Index('idx_hito_entrega_orden', 'plan_entrega_id', 'orden'),
    )

    def __repr__(self):
        return f'<HitoEntrega {self.titulo}>'

class OrdenFabricacion(db.Model):
    __tablename__ = 'ordenes_fabricacion'

    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    glosa = db.Column(db.Text)
    cantidad_tableros = db.Column(db.Integer)
    prioridad = db.Column(db.Enum(PrioridadOrden), default=PrioridadOrden.MEDIA, nullable=False)
    prioridad_numerica = db.Column(db.Integer, default=3)  # Sistema dinámico P1-P50
    fecha_entrega_fabrica = db.Column(db.Date)
    fecha_entrega_embalaje = db.Column(db.Date)
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
    responsable_user = db.relationship('User', foreign_keys=[responsable])
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_of_proyecto', 'proyecto_id'),
        Index('idx_of_contrato', 'contrato_id'),
        Index('idx_of_codigo', 'codigo'),
        Index('idx_of_responsable', 'responsable'),
        Index('idx_of_fechas', 'fecha_planificada', 'fecha_inicio'),
    )

    @property
    def area_progreso_actual(self):
        """Obtiene el progreso actual de la orden en el sistema de áreas"""
        try:
            from sqlalchemy.orm import joinedload
            return (db.session.query(OrdenAreaProgreso)
                    .options(
                        joinedload(OrdenAreaProgreso.area),
                        joinedload(OrdenAreaProgreso.estado)
                    )
                    .filter_by(orden_fabricacion_id=self.id, es_actual=True)
                    .first())
        except Exception:
            return None

    @property
    def area_actual(self):
        """Obtiene el área actual de la orden"""
        try:
            progreso = self.area_progreso_actual
            return progreso.area if progreso else None
        except Exception:
            return None

    @property
    def estado_actual(self):
        """Obtiene el estado actual de la orden"""
        try:
            progreso = self.area_progreso_actual
            return progreso.estado if progreso else None
        except Exception:
            return None

    @property
    def fecha_entrega_dinamica(self):
        """Obtiene la fecha de entrega apropiada según el área actual"""
        try:
            current_progress = self.area_progreso_actual
            if not current_progress or not current_progress.area:
                return self.fecha_entrega_fabrica

            area_tipo = current_progress.area.tipo.value

            if area_tipo == 'fabrica':
                return self.fecha_entrega_fabrica
            elif area_tipo == 'embalaje':
                return self.fecha_entrega_embalaje
            elif area_tipo in ['bodega', 'despacho']:
                # Return contract delivery date
                if self.contrato:
                    if self.contrato.plan_entrega:
                        from models import HitoEntrega, EstadoHitoEntrega
                        from datetime import date

                        next_hito = (db.session.query(HitoEntrega)
                                   .filter_by(plan_entrega_id=self.contrato.plan_entrega.id)
                                   .filter(HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE)
                                   .filter(HitoEntrega.fecha_programada >= datetime.now().date())
                                   .order_by(HitoEntrega.fecha_programada.asc())
                                   .first())

                        if next_hito:
                            return next_hito.fecha_programada

                    return self.contrato.fecha_entrega_comprometida
                return self.fecha_entrega_fabrica
            else:
                return self.fecha_entrega_fabrica

        except Exception:
            return self.fecha_entrega_fabrica

    @property
    def days_remaining_dynamic(self):
        """Calcula días restantes usando la fecha de entrega dinámica"""
        try:
            fecha_entrega = self.fecha_entrega_dinamica
            if fecha_entrega:
                from datetime import date
                today = datetime.now().date()
                return (fecha_entrega - today).days
            return None
        except Exception:
            return None

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
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    hito_entrega_id = db.Column(db.Integer, db.ForeignKey('hitos_entrega.id'), nullable=True)
    numero_despacho = db.Column(db.String(50), unique=True, nullable=False)
    estado = db.Column(db.Enum(EstadoDespacho), default=EstadoDespacho.PROGRAMADO, nullable=False)
    fecha_programada = db.Column(db.Date)
    fecha_envio = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    destino = db.Column(db.Text, nullable=False)
    contacto_destino = db.Column(db.String(200))
    telefono_contacto = db.Column(db.String(50))
    observaciones = db.Column(db.Text)
    responsable_nombre = db.Column(db.String(200))
    numero_guias_despacho = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    adjuntos = db.relationship('DespachoAdjunto', backref='despacho', lazy=True, cascade='all, delete-orphan')
    contrato = db.relationship('Contrato', foreign_keys=[contrato_id])
    hito_entrega = db.relationship('HitoEntrega', foreign_keys=[hito_entrega_id], overlaps="despachos,hito_entrega_rel")
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_despacho_proyecto', 'proyecto_id'),
        Index('idx_despacho_contrato', 'contrato_id'),
        Index('idx_despacho_hito', 'hito_entrega_id'),
        Index('idx_despacho_numero', 'numero_despacho'),
        Index('idx_despacho_estado', 'estado'),
        Index('idx_despacho_responsable_nombre', 'responsable_nombre'),
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

class DespachoOrdenFabricacion(db.Model):
    __tablename__ = 'despacho_ordenes_fabricacion'

    id = db.Column(db.Integer, primary_key=True)
    despacho_id = db.Column(db.Integer, db.ForeignKey('despachos.id'), nullable=False)
    orden_fabricacion_id = db.Column(db.Integer, db.ForeignKey('ordenes_fabricacion.id'), nullable=False)
    tipo_despacho = db.Column(db.Enum(TipoDespacho), nullable=False)
    cantidad_despachada = db.Column(db.Numeric(10, 3), nullable=False)
    cantidad_total = db.Column(db.Numeric(10, 3), nullable=False)
    observaciones = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    despacho = db.relationship('Despacho', backref=db.backref('ordenes_fabricacion_detalle', lazy=True))
    orden_fabricacion = db.relationship('OrdenFabricacion', backref=db.backref('despachos_detalle', lazy=True))
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_despacho_of_despacho', 'despacho_id'),
        Index('idx_despacho_of_orden', 'orden_fabricacion_id'),
        Index('idx_despacho_of_tipo', 'tipo_despacho'),
        # Constraint para evitar duplicados
        db.UniqueConstraint('despacho_id', 'orden_fabricacion_id', name='uq_despacho_orden_fabricacion'),
    )

    @property
    def porcentaje_despachado(self):
        """Calcula el porcentaje despachado de esta OF en este despacho"""
        if self.cantidad_total and self.cantidad_total > 0:
            return (self.cantidad_despachada / self.cantidad_total) * 100
        return 0

    @property
    def cantidad_pendiente(self):
        """Calcula la cantidad pendiente por despachar"""
        return self.cantidad_total - self.cantidad_despachada

    def __repr__(self):
        return f'<DespachoOrdenFabricacion D:{self.despacho_id} OF:{self.orden_fabricacion_id}>'

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
    # TODO: tiempo_total_area_horas = db.Column(db.Numeric(10, 2))  # Tiempo real que pasó en esta área (calculado al salir)
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


class ProyectoAdjunto(db.Model):
    __tablename__ = 'proyecto_adjuntos'

    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.Enum(TipoAdjunto), default=TipoAdjunto.ESPECIFICACION, nullable=False)
    descripcion = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    proyecto = db.relationship('Proyecto', backref='adjuntos')
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_proyecto_adjunto_proyecto', 'proyecto_id'),
        Index('idx_proyecto_adjunto_tipo', 'tipo'),
    )

    def __repr__(self):
        return f'<ProyectoAdjunto {self.filename}>'


class ObjetivoMensual(db.Model):
    __tablename__ = 'objetivos_mensuales'

    id = db.Column(db.Integer, primary_key=True)
    año = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)  # 1-12
    objetivo_provision = db.Column(db.Numeric(15, 2))
    objetivo_instalacion = db.Column(db.Numeric(15, 2))
    notas = db.Column(db.Text)

    # Revenue Management fields
    buffer_pp = db.Column(db.Numeric(5, 2), default=2.0)  # Buffer sobre Break Even
    utilidad_objetivo_clp = db.Column(db.Numeric(15, 2), default=0)  # Utilidad objetivo en CLP
    margen_real_pct = db.Column(db.Numeric(5, 2))  # Margen real del mes
    adjudicado_facturacion = db.Column(db.Numeric(15, 2))  # Facturación adjudicada real
    presupuesto_facturacion = db.Column(db.Numeric(15, 2))  # Presupuesto de facturación

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


class ComisionVendedor(db.Model):
    __tablename__ = 'comisiones_vendedor'

    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    comision_provision_pct = db.Column(db.Numeric(5, 2), default=3.0, nullable=False)  # Porcentaje comisión provisión
    comision_instalacion_pct = db.Column(db.Numeric(5, 2), default=3.0, nullable=False)  # Porcentaje comisión instalación
    activo = db.Column(db.Boolean, default=True, nullable=False)
    notas = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    vendedor = db.relationship('User', foreign_keys=[vendedor_id])
    creator = db.relationship('User', foreign_keys=[created_by])

    # Constraints
    __table_args__ = (
        UniqueConstraint('vendedor_id', name='uq_comision_vendedor'),
        Index('idx_comision_vendedor', 'vendedor_id'),
        Index('idx_comision_activo', 'activo'),
    )

    def __repr__(self):
        return f'<ComisionVendedor {self.vendedor.nombre_completo if self.vendedor else self.vendedor_id}>'


# Modelos para calendario de eventos

class EventoEntrega(db.Model):
    __tablename__ = 'eventos_entrega'

    id = db.Column(db.String(50), primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=True)
    hito_entrega_id = db.Column(db.Integer, db.ForeignKey('hitos_entrega.id'), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    fecha_evento = db.Column(db.Date, nullable=False)
    hora_evento = db.Column(db.Time)
    tipo_evento = db.Column(db.Enum(TipoEvento), nullable=False)
    estado = db.Column(db.Enum(EstadoEvento), default=EstadoEvento.PENDIENTE, nullable=False)
    prioridad = db.Column(db.Enum(PrioridadEvento), default=PrioridadEvento.MEDIA, nullable=False)
    recordatorio_dias = db.Column(db.Integer, default=1)
    recordatorio_enviado = db.Column(db.Boolean, default=False, nullable=False)
    notas = db.Column(db.Text)
    fecha_completado = db.Column(db.DateTime)
    completado_por = db.Column(db.String, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    contrato = db.relationship('Contrato', foreign_keys=[contrato_id])
    proyecto = db.relationship('Proyecto', foreign_keys=[proyecto_id], overlaps="eventos_entrega")
    hito_entrega = db.relationship('HitoEntrega', foreign_keys=[hito_entrega_id], overlaps="evento_entrega,hito")
    creator = db.relationship('User', foreign_keys=[created_by])
    completed_by_user = db.relationship('User', foreign_keys=[completado_por])

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


class EstadoPago(db.Model):
    __tablename__ = 'estados_pago'
    
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    numero_documento = db.Column(db.String(100))  # Número de factura, boleta, etc.
    tipo_estado = db.Column(db.Enum(TipoEstadoPago), nullable=False)
    fecha_estado = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Numeric(15, 2))
    descripcion = db.Column(db.Text)
    fecha_programada_pago = db.Column(db.Date)  # Para pagos programados
    
    # Campos para tracking de inflación UF
    monto_uf = db.Column(db.Numeric(15, 4))  # Monto en UF si aplica
    valor_uf_fecha_estado = db.Column(db.Numeric(15, 2))  # Valor UF en fecha del estado
    monto_clp_equivalente = db.Column(db.Numeric(15, 2))  # Monto CLP equivalente calculado
    ganancia_perdida_inflacion = db.Column(db.Numeric(15, 2))  # Ganancia/pérdida por inflación
    moneda_original = db.Column(db.String(3), default='CLP')  # 'CLP' o 'UF'
    fecha_conversion_uf = db.Column(db.Date)  # Fecha de conversión UF utilizada
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    contrato = db.relationship('Contrato', backref='estados_pago')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_estado_pago_contrato', 'contrato_id'),
        Index('idx_estado_pago_tipo', 'tipo_estado'),
        Index('idx_estado_pago_fecha', 'fecha_estado'),
        Index('idx_estado_pago_moneda', 'moneda_original'),
        Index('idx_estado_pago_inflacion', 'ganancia_perdida_inflacion'),
    )
    
    def __repr__(self):
        return f'<EstadoPago {self.contrato.numero_oc}-{self.tipo_estado.value}>'
    
    @property
    def efectos_inflacion(self):
        """Calcula efectos de inflación para estados de pago UF"""
        if self.moneda_original != 'UF' or not self.monto_uf:
            return None
            
        from services.uf_conversion_service import UfConversionService
        from decimal import Decimal
        import datetime
        
        # Si es facturación en UF
        if self.tipo_estado == TipoEstadoPago.FACTURADO:
            conversion_actual = UfConversionService.convert_uf_to_clp(
                Decimal(str(self.monto_uf))
            )
            if conversion_actual and self.valor_uf_fecha_estado:
                monto_clp_original = Decimal(str(self.monto_uf)) * Decimal(str(self.valor_uf_fecha_estado))
                monto_clp_actual = conversion_actual['clp_amount']
                diferencia = monto_clp_actual - monto_clp_original
                
                return {
                    'monto_uf': self.monto_uf,
                    'valor_uf_facturacion': self.valor_uf_fecha_estado,
                    'valor_uf_actual': conversion_actual['valor_uf'],
                    'monto_clp_facturacion': monto_clp_original,
                    'monto_clp_actual': monto_clp_actual,
                    'ganancia_perdida': diferencia,
                    'porcentaje_variacion': (diferencia / monto_clp_original * 100) if monto_clp_original > 0 else 0
                }
        
        # Si es pago en CLP de factura UF
        elif self.tipo_estado == TipoEstadoPago.PAGADO:
            # Buscar el estado FACTURADO correspondiente para comparar
            estado_facturado = None
            for estado in self.contrato.estados_pago:
                if (estado.tipo_estado == TipoEstadoPago.FACTURADO and 
                    estado.numero_documento and estado.numero_documento == self.numero_documento):
                    estado_facturado = estado
                    break
            
            if estado_facturado and estado_facturado.monto_uf:
                # Calcular la ganancia/pérdida respecto al monto facturado
                monto_facturado_uf_clp = (Decimal(str(estado_facturado.monto_uf)) * 
                                        Decimal(str(self.valor_uf_fecha_estado)))
                diferencia = Decimal(str(self.monto)) - monto_facturado_uf_clp
                
                return {
                    'monto_facturado_uf': estado_facturado.monto_uf,
                    'valor_uf_facturacion': estado_facturado.valor_uf_fecha_estado,
                    'valor_uf_pago': self.valor_uf_fecha_estado,
                    'monto_clp_facturado': monto_facturado_uf_clp,
                    'monto_clp_pagado': self.monto,
                    'ganancia_perdida': diferencia,
                    'porcentaje_variacion': (diferencia / monto_facturado_uf_clp * 100) if monto_facturado_uf_clp > 0 else 0
                }
        
        return None


# =============================================================================
# MODELOS FINANCIEROS
# =============================================================================

class TipoMovimiento(Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    TRANSFERENCIA = "TRANSFERENCIA"

class TipoCentroCosto(Enum):
    PROYECTO = "PROYECTO"
    AREA = "AREA"
    COMPARTIDO = "COMPARTIDO"

class EstadoMovimiento(Enum):
    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"

class CategoriaCosto(Enum):
    """Categorías de costos para manufactura chilena"""
    MATERIALES = "MATERIALES"
    INSTALACION = "INSTALACIÓN"
    GASTO_GARANTIAS = "GASTO GARANTÍAS"
    FLETES = "FLETES"
    OTROS_GASTOS_MENORES = "OTROS GASTOS MENORES"

class CuentaBancaria(db.Model):
    __tablename__ = 'cuentas_bancarias'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    numero_cuenta = db.Column(db.String(50))
    banco = db.Column(db.String(100))
    tipo_cuenta = db.Column(db.String(50))  # Corriente, Vista, Ahorro
    saldo_actual = db.Column(db.Numeric(15, 2), default=0)
    moneda = db.Column(db.String(3), default='CLP', nullable=False)
    activa = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    movimientos = db.relationship('MovimientoFinanciero', backref='cuenta_bancaria', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by])
    
    def __repr__(self):
        return f'<CuentaBancaria {self.nombre}>'

class CentroCosto(db.Model):
    __tablename__ = 'centros_costo'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.Enum(TipoCentroCosto), nullable=False)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=True)
    presupuesto_mensual = db.Column(db.Numeric(15, 2))
    responsable_id = db.Column(db.String, db.ForeignKey('users.id'))
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    proyecto = db.relationship('Proyecto', backref='centros_costo')
    responsable = db.relationship('User', foreign_keys=[responsable_id])
    movimientos = db.relationship('MovimientoFinanciero', backref='centro_costo', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_centro_costo_tipo', 'tipo'),
        Index('idx_centro_costo_proyecto', 'proyecto_id'),
    )
    
    def __repr__(self):
        return f'<CentroCosto {self.codigo}-{self.nombre}>'

class MovimientoFinanciero(db.Model):
    __tablename__ = 'movimientos_financieros'
    
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.Enum(TipoMovimiento), nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    referencia = db.Column(db.String(100))  # Número de factura, boleta, etc.
    
    # Relaciones opcionales
    cuenta_bancaria_id = db.Column(db.Integer, db.ForeignKey('cuentas_bancarias.id'))
    centro_costo_id = db.Column(db.Integer, db.ForeignKey('centros_costo.id'))
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'))
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'))
    
    # Estado y tracking
    estado = db.Column(db.Enum(EstadoMovimiento), default=EstadoMovimiento.CONFIRMADO, nullable=False)
    fecha_confirmacion = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    proyecto = db.relationship('Proyecto', backref='movimientos_financieros')
    contrato = db.relationship('Contrato', backref='movimientos_financieros')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_movimiento_fecha', 'fecha'),
        Index('idx_movimiento_tipo', 'tipo'),
        Index('idx_movimiento_proyecto', 'proyecto_id'),
        Index('idx_movimiento_contrato', 'contrato_id'),
        Index('idx_movimiento_centro_costo', 'centro_costo_id'),
    )
    
    def __repr__(self):
        return f'<MovimientoFinanciero {self.fecha}-{self.tipo.value}-{self.monto}>'


# =============================================================================
# SISTEMA DE PERMISOS DINÁMICOS
# =============================================================================

class Modulo(db.Model):
    """Módulos del sistema para gestión de permisos"""
    __tablename__ = 'modulos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.String(500))
    codigo = db.Column(db.String(50), unique=True, nullable=False)  # ej: 'clientes', 'proyectos'
    activo = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    permisos_rol = db.relationship('PermisoRol', back_populates='modulo', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<Modulo {self.nombre}>'


class PermisoRol(db.Model):
    """Permisos específicos por rol y módulo"""
    __tablename__ = 'permisos_rol'

    id = db.Column(db.Integer, primary_key=True)
    rol = db.Column(db.Enum(RolUsuario), nullable=False)
    modulo_id = db.Column(db.Integer, db.ForeignKey('modulos.id'), nullable=False)
    tipo_permiso = db.Column(db.Enum(TipoPermiso), nullable=False)
    permitido = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    updated_by = db.Column(db.String, db.ForeignKey('users.id'))

    # Relationships
    modulo = db.relationship('Modulo', back_populates='permisos_rol')
    updater = db.relationship('User', foreign_keys=[updated_by])

    # Constraints
    __table_args__ = (
        UniqueConstraint('rol', 'modulo_id', 'tipo_permiso', name='uk_permiso_rol_modulo_tipo'),
        Index('idx_permiso_rol', 'rol'),
        Index('idx_permiso_modulo', 'modulo_id'),
        Index('idx_permiso_tipo', 'tipo_permiso'),
    )

    def __repr__(self):
        return f'<PermisoRol {self.rol.value}-{self.modulo.codigo if self.modulo else "None"}-{self.tipo_permiso.value}>'


class AuditoriaPermisos(db.Model):
    """Auditoría de cambios en permisos"""
    __tablename__ = 'auditoria_permisos'

    id = db.Column(db.Integer, primary_key=True)
    rol = db.Column(db.Enum(RolUsuario), nullable=False)
    modulo_codigo = db.Column(db.String(50), nullable=False)
    tipo_permiso = db.Column(db.Enum(TipoPermiso), nullable=False)
    valor_anterior = db.Column(db.Boolean)
    valor_nuevo = db.Column(db.Boolean, nullable=False)
    accion = db.Column(db.String(50), nullable=False)  # 'created', 'updated', 'deleted'

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_auditoria_rol', 'rol'),
        Index('idx_auditoria_fecha', 'created_at'),
        Index('idx_auditoria_modulo', 'modulo_codigo'),
    )

    def __repr__(self):
        return f'<AuditoriaPermisos {self.rol.value}-{self.modulo_codigo}-{self.tipo_permiso.value}>'

class BitacoraProyecto(db.Model):
    __tablename__ = 'bitacora_proyecto'

    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    usuario_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.Enum(TipoBitacora), default=TipoBitacora.GENERAL, nullable=False)
    fecha_comentario = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    proyecto = db.relationship('Proyecto', backref='bitacora', lazy=True)
    usuario = db.relationship('User', foreign_keys=[usuario_id])

    # Indexes for performance
    __table_args__ = (
        Index('idx_bitacora_proyecto', 'proyecto_id'),
        Index('idx_bitacora_fecha', 'fecha_comentario'),
        Index('idx_bitacora_tipo', 'tipo'),
    )

    def __repr__(self):
        return f'<BitacoraProyecto {self.id}: {self.proyecto_id}>'


class NotificationPreferences(db.Model):
    """Preferencias de notificación por usuario"""
    __tablename__ = 'notification_preferences'
    
    id = db.Column(db.String, primary_key=True, default=lambda: str(db.func.gen_random_uuid()))
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    # Preferencias específicas por tipo de notificación
    nuevo_proyecto_email = db.Column(db.Boolean, default=True)
    comentario_bitacora_email = db.Column(db.Boolean, default=True) 
    cambio_estado_of_email = db.Column(db.Boolean, default=True)
    vencimiento_contrato_email = db.Column(db.Boolean, default=True)
    retraso_proyecto_email = db.Column(db.Boolean, default=True)
    
    # Configuraciones generales
    email_enabled = db.Column(db.Boolean, default=True)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    user = db.relationship('User', backref='notification_preferences')
    
    # Indexes
    __table_args__ = (
        Index('idx_notification_preferences_user', 'user_id'),
    )
    
    def __repr__(self):
        return f"<NotificationPreferences(user_id={self.user_id})>"


class CostoProyecto(db.Model):
    """Costos registrados desde el ERP para proyectos"""
    __tablename__ = 'costos_proyecto'
    
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    categoria = db.Column(db.Enum(CategoriaCosto), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    fecha_registro = db.Column(db.Date, nullable=False)
    
    # Referencia al ERP (opcional)
    codigo_erp = db.Column(db.String(50))  # Para linking con ERP Mobikit
    documento_referencia = db.Column(db.String(100))  # Factura, guía, etc.
    proveedor = db.Column(db.String(200))
    
    # Campos de auditoría
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String, db.ForeignKey('users.id'))
    
    # Relationships
    proyecto = db.relationship('Proyecto', backref='costos')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_costo_proyecto', 'proyecto_id'),
        Index('idx_costo_categoria', 'categoria'),
        Index('idx_costo_fecha', 'fecha_registro'),
        Index('idx_costo_erp', 'codigo_erp'),
    )
    
    def __repr__(self):
        return f'<CostoProyecto {self.proyecto_id}-{self.categoria.value}-{self.monto}>'