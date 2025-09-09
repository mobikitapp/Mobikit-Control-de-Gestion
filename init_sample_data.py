
#!/usr/bin/env python3
"""
Script para inicializar datos de ejemplo en la base de datos de Mobikit
Actualizado para los nuevos campos y estructura del modelo
"""

import os
import sys
from datetime import datetime, timedelta, date
from decimal import Decimal
import random

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import (
    User, Cliente, Proyecto, Contrato, OrdenFabricacion, OrdenFabricacionItem,
    Despacho, ContratoAdjunto, PlanEntrega, HitoEntrega, EventoEntrega,
    Area, AreaEstado, OrdenAreaProgreso, TareaComercial, ObjetivoMensual,
    CategoriaMuebleModel, SubcategoriaMuebleModel,
    RolUsuario, EstadoContrato, EstadoComercial, EstadoOF, EstadoDespacho,
    TipoDocumento, TipoEvento, EstadoEvento, PrioridadEvento,
    CategoriaMueble, SubcategoriaCocina, SubcategoriaCloset,
    TipoArea, EstadoPendientesFabricacion, EstadoFabrica, EstadoEmbalaje,
    EstadoBodega, EstadoDespachoArea, EstadoHitoEntrega,
    local_now, utc_now
)

def init_sample_data():
    """Inicializa datos de ejemplo para pruebas"""
    with app.app_context():
        print("🚀 Inicializando datos de ejemplo...")
        
        try:
            # Limpiar datos existentes
            print("🧹 Limpiando datos existentes...")
            clear_existing_data()
            
            # 1. Crear áreas del sistema
            print("📍 Creando áreas del sistema...")
            create_system_areas()
            
            # 2. Crear categorías de muebles
            print("🏷️ Creando categorías de muebles...")
            create_furniture_categories()
            
            # 3. Crear usuarios de ejemplo
            print("👥 Creando usuarios de ejemplo...")
            create_sample_users()
            
            # 4. Crear clientes de ejemplo
            print("🏢 Creando clientes de ejemplo...")
            create_sample_clients()
            
            # 5. Crear proyectos de ejemplo
            print("📋 Creando proyectos de ejemplo...")
            create_sample_projects()
            
            # 6. Crear contratos de ejemplo
            print("📄 Creando contratos de ejemplo...")
            create_sample_contracts()
            
            # 7. Crear órdenes de fabricación de ejemplo
            print("🔧 Creando órdenes de fabricación de ejemplo...")
            create_sample_fabrication_orders()
            
            # 8. Crear despachos de ejemplo
            print("🚚 Creando despachos de ejemplo...")
            create_sample_despachos()
            
            # 9. Crear eventos de entrega
            print("📅 Creando eventos de entrega...")
            create_sample_events()
            
            # 10. Crear objetivos mensuales
            print("🎯 Creando objetivos mensuales...")
            create_sample_monthly_objectives()
            
            db.session.commit()
            print("✅ Datos de ejemplo creados exitosamente!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al crear datos de ejemplo: {e}")
            raise

def clear_existing_data():
    """Limpia datos existentes (excepto usuarios OAuth)"""
    # Eliminar en orden para respetar las foreign keys
    OrdenAreaProgreso.query.delete()
    OrdenFabricacionItem.query.delete()
    OrdenFabricacion.query.delete()
    Despacho.query.delete()
    EventoEntrega.query.delete()
    HitoEntrega.query.delete()
    PlanEntrega.query.delete()
    ContratoAdjunto.query.delete()
    Contrato.query.delete()
    TareaComercial.query.delete()
    Proyecto.query.delete()
    Cliente.query.delete()
    ObjetivoMensual.query.delete()
    
    # Limpiar áreas y estados si existen
    AreaEstado.query.delete()
    Area.query.delete()
    
    # Limpiar categorías
    SubcategoriaMuebleModel.query.delete()
    CategoriaMuebleModel.query.delete()
    
    db.session.flush()

def create_system_areas():
    """Crea las áreas del sistema de producción"""
    areas_data = [
        {
            'tipo': TipoArea.PENDIENTES_FABRICACION,
            'nombre': 'Pendientes de Fabricación',
            'descripcion': 'Área para órdenes pendientes de aprobación y diseño',
            'orden_secuencia': 1,
            'color_hex': '#ffc107',
            'estados': [
                {'codigo': 'pendiente_aprobacion_diseño', 'nombre': 'Pendiente Aprobación Diseño', 'orden': 1, 'es_inicial': True},
                {'codigo': 'aprobado', 'nombre': 'Aprobado', 'orden': 2, 'es_final': True}
            ]
        },
        {
            'tipo': TipoArea.FABRICA,
            'nombre': 'Fábrica',
            'descripcion': 'Área de producción y manufactura',
            'orden_secuencia': 2,
            'color_hex': '#0d6efd',
            'estados': [
                {'codigo': 'enviado_a_fabricacion', 'nombre': 'Enviado a Fabricación', 'orden': 1, 'es_inicial': True},
                {'codigo': 'seccionando', 'nombre': 'Seccionando', 'orden': 2},
                {'codigo': 'enchapando', 'nombre': 'Enchapando', 'orden': 3},
                {'codigo': 'mecanizando', 'nombre': 'Mecanizando', 'orden': 4},
                {'codigo': 'fabricacion_completa', 'nombre': 'Fabricación Completa', 'orden': 5, 'es_final': True}
            ]
        },
        {
            'tipo': TipoArea.EMBALAJE,
            'nombre': 'Embalaje',
            'descripcion': 'Área de preparación y embalaje',
            'orden_secuencia': 3,
            'color_hex': '#fd7e14',
            'estados': [
                {'codigo': 'pendiente_de_embalar', 'nombre': 'Pendiente de Embalar', 'orden': 1, 'es_inicial': True},
                {'codigo': 'embalando', 'nombre': 'Embalando', 'orden': 2},
                {'codigo': 'embalaje_listo', 'nombre': 'Embalaje Listo', 'orden': 3, 'es_final': True}
            ]
        },
        {
            'tipo': TipoArea.BODEGA,
            'nombre': 'Bodega',
            'descripcion': 'Área de almacenamiento y preparación para despacho',
            'orden_secuencia': 4,
            'color_hex': '#198754',
            'estados': [
                {'codigo': 'listo_para_despacho', 'nombre': 'Listo para Despacho', 'orden': 1, 'es_inicial': True, 'es_final': False},
                {'codigo': 'programado_para_despacho', 'nombre': 'Programado para Despacho', 'orden': 2, 'es_inicial': False, 'es_final': True}
            ]
        },
        {
            'tipo': TipoArea.DESPACHO,
            'nombre': 'Despacho',
            'descripcion': 'Área de logística y entrega',
            'orden_secuencia': 5,
            'color_hex': '#6f42c1',
            'estados': [
                {'codigo': 'despachado', 'nombre': 'Despachado', 'orden': 1, 'es_inicial': True, 'es_final': True}
            ]
        }
    ]
    
    for area_data in areas_data:
        estados_data = area_data.pop('estados', [])
        area = Area(**area_data)
        db.session.add(area)
        db.session.flush()
        
        for estado_data in estados_data:
            estado = AreaEstado(
                area_id=area.id,
                codigo=estado_data['codigo'],
                nombre=estado_data['nombre'],
                orden_en_area=estado_data['orden'],
                es_inicial=estado_data['es_inicial'],
                es_final=estado_data['es_final'],
                activo=True
            )
            db.session.add(estado)

def create_furniture_categories():
    """Crea categorías y subcategorías de muebles"""
    # Crear categorías principales
    categorias = [
        {'nombre': CategoriaMueble.COCINA, 'descripcion': 'Muebles de cocina'},
        {'nombre': CategoriaMueble.CLOSET, 'descripcion': 'Closets y vestidores'},
        {'nombre': CategoriaMueble.BANO, 'descripcion': 'Muebles de baño'}
    ]
    
    categoria_cocina = None
    categoria_closet = None
    
    for cat_data in categorias:
        categoria = CategoriaMuebleModel(**cat_data)
        db.session.add(categoria)
        db.session.flush()
        
        if categoria.nombre == CategoriaMueble.COCINA:
            categoria_cocina = categoria
        elif categoria.nombre == CategoriaMueble.CLOSET:
            categoria_closet = categoria
    
    # Crear subcategorías para cocina
    if categoria_cocina:
        subcategorias_cocina = [
            {'categoria_id': categoria_cocina.id, 'nombre_cocina': SubcategoriaCocina.BASES, 'descripcion': 'Muebles base de cocina'},
            {'categoria_id': categoria_cocina.id, 'nombre_cocina': SubcategoriaCocina.MURALES, 'descripcion': 'Muebles murales de cocina'},
            {'categoria_id': categoria_cocina.id, 'nombre_cocina': SubcategoriaCocina.KITS, 'descripcion': 'Kits completos de cocina'},
            {'categoria_id': categoria_cocina.id, 'nombre_cocina': SubcategoriaCocina.CUBIERTAS, 'descripcion': 'Cubiertas de cocina'}
        ]
        
        for subcat_data in subcategorias_cocina:
            subcategoria = SubcategoriaMuebleModel(**subcat_data)
            db.session.add(subcategoria)
    
    # Crear subcategorías para closet
    if categoria_closet:
        subcategorias_closet = [
            {'categoria_id': categoria_closet.id, 'nombre_closet': SubcategoriaCloset.INTERIORES, 'descripcion': 'Interiores de closet'},
            {'categoria_id': categoria_closet.id, 'nombre_closet': SubcategoriaCloset.PIERNAS, 'descripcion': 'Piernas y estructura'},
            {'categoria_id': categoria_closet.id, 'nombre_closet': SubcategoriaCloset.PUERTAS, 'descripcion': 'Puertas de closet'}
        ]
        
        for subcat_data in subcategorias_closet:
            subcategoria = SubcategoriaMuebleModel(**subcat_data)
            db.session.add(subcategoria)

def create_sample_users():
    """Crea usuarios de ejemplo (solo si no existen)"""
    usuarios_data = [
        {
            'id': 'admin-001',
            'email': 'admin@mobikit.com',
            'first_name': 'Administrador',
            'last_name': 'Sistema',
            'rol': RolUsuario.ADMIN
        },
        {
            'id': 'ventas-001', 
            'email': 'carlos.mendoza@mobikit.com',
            'first_name': 'Carlos',
            'last_name': 'Mendoza',
            'rol': RolUsuario.VENTAS
        },
        {
            'id': 'operaciones-001',
            'email': 'ana.garcia@mobikit.com', 
            'first_name': 'Ana',
            'last_name': 'García',
            'rol': RolUsuario.OPERACIONES
        },
        {
            'id': 'produccion-001',
            'email': 'luis.rodriguez@mobikit.com',
            'first_name': 'Luis', 
            'last_name': 'Rodríguez',
            'rol': RolUsuario.PRODUCCION
        },
        {
            'id': 'logistica-001',
            'email': 'maria.lopez@mobikit.com',
            'first_name': 'María',
            'last_name': 'López', 
            'rol': RolUsuario.LOGISTICA
        }
    ]
    
    for user_data in usuarios_data:
        existing_user = User.query.filter_by(id=user_data['id']).first()
        if not existing_user:
            user = User(**user_data)
            db.session.add(user)

def create_sample_clients():
    """Crea clientes de ejemplo"""
    clientes_data = [
        {
            'nombre': 'Constructora Moderna Ltda.',
            'rut': '76.123.456-7',
            'condiciones_comerciales': '30 días corridos',
            'contacto_principal': 'Pedro Sánchez', 
            'email_contacto': 'pedro.sanchez@constructoramoderna.cl',
            'telefono_contacto': '+56 2 2234 5678',
            'direccion': 'Av. Providencia 1234, Santiago',
            'created_by': 'ventas-001'
        },
        {
            'nombre': 'Inmobiliaria Elite S.A.',
            'rut': '96.789.012-3',
            'condiciones_comerciales': '45 días fecha factura',
            'contacto_principal': 'Carmen Ruiz',
            'email_contacto': 'carmen.ruiz@inmobiliariaelite.cl', 
            'telefono_contacto': '+56 2 3345 6789',
            'direccion': 'Los Leones 567, Las Condes',
            'created_by': 'ventas-001'
        },
        {
            'nombre': 'Decoraciones Premium SpA',
            'rut': '77.456.789-0',
            'condiciones_comerciales': '60 días corridos',
            'contacto_principal': 'Ricardo Torres',
            'email_contacto': 'ricardo.torres@decoracionespremium.cl',
            'telefono_contacto': '+56 2 4456 7890', 
            'direccion': 'Mall Plaza Norte Local 45, Huechuraba',
            'created_by': 'ventas-001'
        },
        {
            'nombre': 'Oficinas Corporativas Ltda.',
            'rut': '85.234.567-1',
            'condiciones_comerciales': '30 días fecha factura',
            'contacto_principal': 'Sofía Morales',
            'email_contacto': 'sofia.morales@oficinascorporativas.cl',
            'telefono_contacto': '+56 2 5567 8901',
            'direccion': 'Providencia 890, Providencia',
            'created_by': 'ventas-001'
        }
    ]
    
    for cliente_data in clientes_data:
        cliente = Cliente(**cliente_data)
        db.session.add(cliente)

def create_sample_projects():
    """Crea proyectos de ejemplo"""
    # Obtener clientes e IDs de usuarios
    clientes = Cliente.query.all()
    
    proyectos_data = [
        {
            'cliente_id': clientes[0].id if clientes else 1,
            'nombre': 'Proyecto Torres del Sol - Fase 1',
            'descripcion': 'Cocinas integrales para 24 departamentos en Las Condes',
            'fecha_inicio': date.today() - timedelta(days=30),
            'fecha_fin_estimada': date.today() + timedelta(days=60),
            'responsable': 'operaciones-001',
            'vendedor_id': 'ventas-001',
            'estado_comercial': EstadoComercial.ADJUDICADO,
            'monto_provision_presupuestado': Decimal('48000000'),
            'margen_venta_provision': Decimal('25.00'),
            'monto_instalacion_presupuestado': Decimal('12000000'),
            'margen_venta_instalacion': Decimal('30.00'),
            'fecha_presupuesto': date.today() - timedelta(days=45),
            'fecha_adjudicacion': date.today() - timedelta(days=30),
            'notas_comerciales': 'Cliente premium, pago al contado con descuento',
            'created_by': 'ventas-001'
        },
        {
            'cliente_id': clientes[1].id if len(clientes) > 1 else 1,
            'nombre': 'Residencial Los Robles',
            'descripcion': 'Closets modulares para 15 casas en condominio',
            'fecha_inicio': date.today() - timedelta(days=15),
            'fecha_fin_estimada': date.today() + timedelta(days=45),
            'responsable': 'operaciones-001',
            'vendedor_id': 'ventas-001',
            'estado_comercial': EstadoComercial.EN_DESARROLLO,
            'monto_provision_presupuestado': Decimal('22500000'),
            'margen_venta_provision': Decimal('22.00'),
            'fecha_presupuesto': date.today() - timedelta(days=20),
            'fecha_adjudicacion': date.today() - timedelta(days=15),
            'created_by': 'ventas-001'
        },
        {
            'cliente_id': clientes[2].id if len(clientes) > 2 else 1,
            'nombre': 'Oficinas Central Park',
            'descripcion': 'Mobiliario ejecutivo para nuevas oficinas corporativas',
            'fecha_inicio': date.today() - timedelta(days=5),
            'fecha_fin_estimada': date.today() + timedelta(days=35),
            'responsable': 'operaciones-001',
            'vendedor_id': 'ventas-001',
            'estado_comercial': EstadoComercial.EN_DESARROLLO,
            'monto_provision_presupuestado': Decimal('18750000'),
            'margen_venta_provision': Decimal('28.00'),
            'monto_instalacion_presupuestado': Decimal('3750000'),
            'margen_venta_instalacion': Decimal('25.00'),
            'fecha_presupuesto': date.today() - timedelta(days=10),
            'fecha_adjudicacion': date.today() - timedelta(days=5),
            'created_by': 'ventas-001'
        },
        {
            'cliente_id': clientes[3].id if len(clientes) > 3 else 1,
            'nombre': 'Remodelación Casa Particular',
            'descripcion': 'Cocina integral y baños para casa en La Reina',
            'fecha_inicio': date.today(),
            'fecha_fin_estimada': date.today() + timedelta(days=30),
            'responsable': 'operaciones-001',
            'vendedor_id': 'ventas-001',
            'estado_comercial': EstadoComercial.PRESUPUESTADO,
            'monto_provision_presupuestado': Decimal('9500000'),
            'margen_venta_provision': Decimal('30.00'),
            'monto_instalacion_presupuestado': Decimal('2000000'),
            'margen_venta_instalacion': Decimal('35.00'),
            'fecha_presupuesto': date.today() - timedelta(days=3),
            'notas_comerciales': 'Cliente en evaluación, se espera respuesta esta semana',
            'created_by': 'ventas-001'
        }
    ]
    
    for proyecto_data in proyectos_data:
        proyecto = Proyecto(**proyecto_data)
        db.session.add(proyecto)

def create_sample_contracts():
    """Crea contratos de ejemplo"""
    proyectos = Proyecto.query.filter(Proyecto.estado_comercial.in_([
        EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO
    ])).all()
    
    for i, proyecto in enumerate(proyectos[:3]):  # Solo primeros 3 proyectos
        contrato_data = {
            'proyecto_id': proyecto.id,
            'tipo_documento': TipoDocumento.ORDEN_COMPRA,
            'numero_oc': f'OC-{2024}-{(i+1):03d}',
            'monto_total': (proyecto.monto_provision_presupuestado or 0) + (proyecto.monto_instalacion_presupuestado or 0),
            'moneda': 'CLP',
            'estado': EstadoContrato.VIGENTE,
            'fecha_emision': date.today() - timedelta(days=20-i*5),
            'fecha_vencimiento': date.today() + timedelta(days=90),
            'fecha_entrega_comprometida': proyecto.fecha_fin_estimada,
            'condiciones_pago': '30% anticipo, 40% avance de obra, 30% entrega',
            'notas': f'Contrato para proyecto {proyecto.nombre}',
            'created_by': 'ventas-001'
        }
        
        contrato = Contrato(**contrato_data)
        db.session.add(contrato)
        db.session.flush()
        
        # Crear plan de entrega para cada contrato
        plan_data = {
            'contrato_id': contrato.id,
            'nombre': f'Plan de Entrega - {proyecto.nombre}',
            'descripcion': f'Plan de entrega en fases para {proyecto.nombre}',
            'created_by': 'operaciones-001'
        }
        
        plan = PlanEntrega(**plan_data)
        db.session.add(plan)
        db.session.flush()
        
        # Crear hitos de entrega
        hitos_data = [
            {
                'plan_entrega_id': plan.id,
                'orden': 1,
                'titulo': 'Entrega Fase 1',
                'descripcion': 'Primera entrega parcial del proyecto',
                'fecha_programada': date.today() + timedelta(days=20),
                'estado': EstadoHitoEntrega.PENDIENTE,
                'created_by': 'operaciones-001'
            },
            {
                'plan_entrega_id': plan.id,
                'orden': 2,
                'titulo': 'Entrega Final',
                'descripcion': 'Entrega final del proyecto completo',
                'fecha_programada': proyecto.fecha_fin_estimada,
                'estado': EstadoHitoEntrega.PENDIENTE,
                'created_by': 'operaciones-001'
            }
        ]
        
        for hito_data in hitos_data:
            hito = HitoEntrega(**hito_data)
            db.session.add(hito)

def create_sample_fabrication_orders():
    """Crea órdenes de fabricación de ejemplo"""
    contratos = Contrato.query.all()
    
    for i, contrato in enumerate(contratos):
        # Crear 2-3 OFs por contrato
        num_ofs = random.randint(2, 3)
        
        for j in range(num_ofs):
            of_data = {
                'proyecto_id': contrato.proyecto_id,
                'contrato_id': contrato.id,
                'codigo': f'OP-{2024}-{(i+1):02d}{(j+1):02d}',
                'descripcion': f'Orden de fabricación {j+1} para {contrato.proyecto.nombre}',
                'glosa': f'Lote {j+1} - {["Cocinas", "Closets", "Muebles varios"][j % 3]}',
                'cantidad_tableros': random.randint(8, 25) if j > 0 else None,  # Primera OF sin tableros para probar validación
                'fecha_entrega_fabrica': date.today() + timedelta(days=15 + j*10),
                'estado': ['pendiente_aprobacion_diseño', 'aprobado', 'seccionando'][j % 3],
                'fecha_planificada': date.today() + timedelta(days=5 + j*3),
                'responsable': 'produccion-001',
                'notas': f'OF generada automáticamente para lote {j+1}',
                'created_by': 'operaciones-001'
            }
            
            # Si el estado es SECCIONANDO o posterior, agregar fecha_inicio
            if of_data['estado'] in ['seccionando', 'enchapando']:
                of_data['fecha_inicio'] = datetime.now() - timedelta(days=random.randint(1, 5))
            
            of = OrdenFabricacion(**of_data)
            db.session.add(of)
            db.session.flush()
            
            # Crear items para cada OF
            items_templates = [
                [
                    {'sku_codigo': 'COC-BASE-001', 'descripcion': 'Mueble base cocina 3.5m', 'cantidad': Decimal('3.5'), 'unidad': 'ML'},
                    {'sku_codigo': 'COC-MUR-001', 'descripcion': 'Muebles murales cocina', 'cantidad': Decimal('2.0'), 'unidad': 'ML'},
                    {'sku_codigo': 'COC-CUB-001', 'descripcion': 'Cubierta de granito', 'cantidad': Decimal('4.2'), 'unidad': 'ML'}
                ],
                [
                    {'sku_codigo': 'CLO-DOR-001', 'descripcion': 'Closet dormitorio principal', 'cantidad': Decimal('1'), 'unidad': 'UN'},
                    {'sku_codigo': 'CLO-SEC-001', 'descripcion': 'Closet dormitorio secundario', 'cantidad': Decimal('1'), 'unidad': 'UN'},
                    {'sku_codigo': 'CLO-PUE-001', 'descripcion': 'Puertas deslizantes', 'cantidad': Decimal('4'), 'unidad': 'UN'}
                ],
                [
                    {'sku_codigo': 'MUE-ESC-001', 'descripcion': 'Escritorio ejecutivo', 'cantidad': Decimal('1'), 'unidad': 'UN'},
                    {'sku_codigo': 'MUE-EST-001', 'descripcion': 'Estantería modular', 'cantidad': Decimal('2'), 'unidad': 'UN'},
                    {'sku_codigo': 'MUE-SIL-001', 'descripcion': 'Sillas ergonómicas', 'cantidad': Decimal('6'), 'unidad': 'UN'}
                ]
            ]
            
            items_data = items_templates[j % len(items_templates)]
            
            for item_data in items_data:
                item_data['of_id'] = of.id
                item_data['notas'] = f'Item para lote {j+1}'
                
                item = OrdenFabricacionItem(**item_data)
                db.session.add(item)

def create_sample_despachos():
    """Crea despachos de ejemplo"""
    # Solo crear despachos para OFs que estén en estado avanzado
    ofs_avanzadas = OrdenFabricacion.query.filter(
        OrdenFabricacion.estado.in_(['seccionando', 'enchapando'])
    ).all()
    
    for i, of in enumerate(ofs_avanzadas[:2]):  # Solo 2 despachos
        despacho_data = {
            'proyecto_id': of.proyecto_id,
            'of_id': of.id,
            'numero_despacho': f'DESP-{2024}-{(i+1):03d}',
            'estado': EstadoDespacho.PROGRAMADO,
            'fecha_programada': date.today() + timedelta(days=10 + i*5),
            'destino': of.proyecto.cliente.direccion,
            'contacto_destino': of.proyecto.cliente.contacto_principal,
            'telefono_contacto': of.proyecto.cliente.telefono_contacto,
            'observaciones': f'Despacho programado para OF {of.codigo}',
            'responsable': 'logistica-001',
            'created_by': 'operaciones-001'
        }
        
        despacho = Despacho(**despacho_data)
        db.session.add(despacho)

def create_sample_events():
    """Crea eventos de entrega de ejemplo"""
    contratos = Contrato.query.all()
    
    for i, contrato in enumerate(contratos):
        evento_data = {
            'id': f'evento-{contrato.id}-{i+1}',
            'proyecto_id': contrato.proyecto_id,
            'contrato_id': contrato.id,
            'titulo': f'Entrega {contrato.proyecto.nombre}',
            'descripcion': f'Entrega programada para proyecto {contrato.proyecto.nombre}',
            'fecha_evento': contrato.fecha_entrega_comprometida or (date.today() + timedelta(days=30)),
            'tipo_evento': TipoEvento.ENTREGA,
            'estado': EstadoEvento.PENDIENTE,
            'prioridad': PrioridadEvento.ALTA if i == 0 else PrioridadEvento.MEDIA,
            'recordatorio_dias': 3,
            'created_by': 'operaciones-001'
        }
        
        evento = EventoEntrega(**evento_data)
        db.session.add(evento)

def create_sample_monthly_objectives():
    """Crea objetivos mensuales de ejemplo"""
    # Crear objetivos para los próximos 3 meses
    for i in range(3):
        fecha_objetivo = date.today().replace(day=1) + timedelta(days=32*i)
        
        objetivo_data = {
            'año': fecha_objetivo.year,
            'mes': fecha_objetivo.month,
            'objetivo_provision': Decimal('50000000'),  # 50M CLP
            'objetivo_instalacion': Decimal('15000000'),  # 15M CLP
            'notas': f'Objetivo para {fecha_objetivo.strftime("%B %Y")}',
            'created_by': 'admin-001'
        }
        
        objetivo = ObjetivoMensual(**objetivo_data)
        db.session.add(objetivo)

def create_sample_tasks():
    """Crea tareas comerciales de ejemplo"""
    proyectos = Proyecto.query.all()
    
    tareas_templates = [
        'Enviar cotización actualizada',
        'Coordinar visita a obra', 
        'Revisar especificaciones técnicas',
        'Programar reunión con cliente',
        'Actualizar cronograma de entrega'
    ]
    
    for proyecto in proyectos[:3]:  # Solo primeros 3 proyectos
        for i, template in enumerate(tareas_templates[:3]):  # Solo 3 tareas por proyecto
            tarea_data = {
                'proyecto_id': proyecto.id,
                'vendedor_id': proyecto.vendedor_id or 'ventas-001',
                'titulo': template,
                'descripcion': f'{template} para {proyecto.nombre}',
                'completada': i == 0,  # Primera tarea completada
                'fecha_limite': date.today() + timedelta(days=random.randint(3, 15)),
                'fecha_completada': datetime.now() - timedelta(days=1) if i == 0 else None,
                'notas': f'Tarea relacionada con {proyecto.nombre}',
                'created_by': 'ventas-001'
            }
            
            tarea = TareaComercial(**tarea_data)
            db.session.add(tarea)

if __name__ == '__main__':
    init_sample_data()
