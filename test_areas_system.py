#!/usr/bin/env python3
from app import app, db
from models import Cliente, Proyecto, OrdenFabricacion, OrdenAreaProgreso, Area, AreaEstado
from datetime import datetime

with app.app_context():
    try:
        # Create test client
        cliente = Cliente(
            nombre='Test Company S.A.',
            rut='12345678-9',
            email_contacto='test@company.com',
            telefono_contacto='+56912345678',
            contacto_principal='Juan Pérez',
            direccion='Santiago, Chile',
            condiciones_comerciales='30 días',
            created_by=None
        )
        db.session.add(cliente)
        db.session.flush()
        
        # Create test project
        proyecto = Proyecto(
            nombre='Proyecto de Prueba',
            cliente_id=cliente.id,
            fecha_inicio=datetime.utcnow(),
            descripcion='Proyecto para probar el sistema de áreas',
            created_by=None
        )
        db.session.add(proyecto)
        db.session.flush()
        
        # Create test OF
        of = OrdenFabricacion(
            codigo='OP-0001',
            proyecto_id=proyecto.id,
            fecha_planificada=datetime.utcnow(),
            descripcion='Orden de prueba para verificar el sistema',
            cantidad_tableros=10,
            created_by=None
        )
        db.session.add(of)
        db.session.flush()
        
        # Initialize OF in area system
        primera_area = db.session.query(Area).filter_by(orden_secuencia=1).first()
        primer_estado = db.session.query(AreaEstado).filter_by(
            area_id=primera_area.id,
            orden_en_area=1
        ).first()
        
        if primera_area and primer_estado:
            progreso = OrdenAreaProgreso(
                orden_fabricacion_id=of.id,
                area_id=primera_area.id,
                estado_id=primer_estado.id,
                fecha_ingreso_area=datetime.utcnow(),
                fecha_cambio_estado=datetime.utcnow()
            )
            db.session.add(progreso)
            db.session.commit()
            
            print(f'✓ Creado cliente: {cliente.nombre}')
            print(f'✓ Creado proyecto: {proyecto.nombre}')
            print(f'✓ Creada OF: {of.codigo}')
            print(f'✓ Inicializada en área: {primera_area.nombre}')
            print(f'✓ Con estado: {primer_estado.nombre}')
            print('\n¡Datos de prueba creados exitosamente!')
        else:
            print('Error: No se encontró la primera área o estado')
            db.session.rollback()
            
    except Exception as e:
        db.session.rollback()
        print(f'Error creando datos de prueba: {str(e)}')
        import traceback
        traceback.print_exc()