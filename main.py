from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
import json
from functools import wraps
import uuid
import sqlite3 # Keep this import for the ALTER TABLE fallback, although its functions are replaced.

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'mobikit_secret_key_2024')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise Exception('DATABASE_URL environment variable is required for deployment')
ADMIN_DEFAULT_PASSWORD = os.getenv('ADMIN_DEFAULT_PASSWORD', 'admin123')

# Tipos de archivos permitidos
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}

# Crear carpeta de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('templates', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, subfolder='despachos'):
    """Guarda un archivo subido y retorna la ruta relativa"""
    if file and allowed_file(file.filename):
        # Crear nombre único para evitar conflictos
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"

        # Crear directorio si no existe
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(upload_path, exist_ok=True)

        # Guardar archivo
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)

        # Retornar ruta relativa para la base de datos
        return f"uploads/{subfolder}/{unique_filename}"
    return None

def delete_file(file_path):
    """Elimina un archivo del sistema de archivos"""
    if file_path:
        full_path = os.path.join('static', file_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                return True
            except Exception as e:
                print(f"Error al eliminar archivo {full_path}: {e}")
    return False

def get_db_connection():
    """Helper function to get database connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Roles disponibles
ROLES = ['admin', 'general', 'diseñador', 'operación', 'embalaje', 'despacho']


def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Ejecutar el schema completo desde el archivo SQL
    try:
        with open('database_schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            cursor.execute(schema_sql)
    except FileNotFoundError:
        # Fallback: crear solo las tablas básicas si no existe el archivo de schema
        create_basic_tables(cursor)

    # Agregar columna archivado si no existe
    try:
        # Check if column exists first
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'proyectos' AND column_name = 'archivado'
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE proyectos ADD COLUMN archivado BOOLEAN DEFAULT FALSE")
    except Exception as e:
        print(f"Error adding 'archivado' column: {e}")


    # Crear usuario admin por defecto si no existe
    cursor.execute('SELECT COUNT(*) FROM usuarios WHERE rol = %s', ('admin',))
    if cursor.fetchone()[0] == 0:
        admin_password = generate_password_hash(ADMIN_DEFAULT_PASSWORD)
        cursor.execute(
            '''
            INSERT INTO usuarios (username, password_hash, rol, nombre, email, activo)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', ('admin', admin_password, 'admin', 'Administrador',
              'admin@mobikit.com', True))

    conn.commit()
    conn.close()


def create_basic_tables(cursor):
    """Crear tablas básicas como fallback"""
    # Note: PostgreSQL uses SERIAL for auto-incrementing primary keys and TEXT for strings.
    # AUTOINCREMENT is SQLite specific.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL,
            nombre TEXT NOT NULL,
            apellido TEXT,
            email TEXT UNIQUE,
            telefono TEXT,
            area_id INTEGER,
            activo BOOLEAN DEFAULT TRUE,
            ultimo_acceso TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            rut TEXT UNIQUE,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            ciudad TEXT,
            region TEXT,
            contacto_principal TEXT,
            observaciones TEXT,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proyectos (
            id SERIAL PRIMARY KEY,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            descripcion TEXT,
            adjudicacion_tipo TEXT DEFAULT 'orden_compra' CHECK (adjudicacion_tipo IN ('contrato', 'orden_compra')),
            estado TEXT DEFAULT 'diseño',
            prioridad TEXT DEFAULT 'media',
            fecha_inicio DATE,
            fecha_entrega DATE,
            fecha_entrega_real DATE,
            diseñador_id INTEGER,
            supervisor_id INTEGER,
            monto_neto DECIMAL(12,2),
            costo_real DECIMAL(12,2),
            observaciones TEXT,
            archivado BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (diseñador_id) REFERENCES usuarios (id),
            FOREIGN KEY (supervisor_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tareas (
            id SERIAL PRIMARY KEY,
            proyecto_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            estado TEXT DEFAULT 'pendiente',
            prioridad TEXT DEFAULT 'media',
            fecha_programada DATE,
            fecha_completada TIMESTAMP,
            usuario_asignado_id INTEGER,
            rol_asignado TEXT,
            tiempo_estimado INTEGER,
            tiempo_real INTEGER,
            observaciones TEXT,
            etapa_fabricacion TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
            FOREIGN KEY (usuario_asignado_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evidencias (
            id SERIAL PRIMARY KEY,
            tarea_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            ruta_archivo TEXT NOT NULL,
            descripcion TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tarea_id) REFERENCES tareas (id)
        )
    ''')


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def role_required(roles):

    def decorator(f):

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] not in roles:
                flash('No tienes permisos para acceder a esta página', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, password_hash, rol, nombre FROM usuarios WHERE username = %s',
            (username, ))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_role'] = user['rol']
            session['user_name'] = user['nombre']
            flash(f'Bienvenido, {user["nombre"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada exitosamente', 'success')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Órdenes de compra pendientes (proyectos con categorías asignadas)
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.estado, p.prioridad,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('en_desarrollo')
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.estado, p.prioridad
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_pendientes = cursor.fetchall()

    # Órdenes en Proceso (tienen órdenes de fabricación activas)
    cursor.execute('''
        SELECT DISTINCT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.prioridad,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa')
        AND p.estado != 'entregado'
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.prioridad
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_proceso_raw = cursor.fetchall()

    # Para cada orden en proceso, obtener sus órdenes de fabricación si existen
    ordenes_proceso = []
    for orden in ordenes_proceso_raw:
        # Check if ordenes_fabricacion table exists
        cursor.execute('''
            SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ordenes_fabricacion')
        ''')
        if cursor.fetchone()[0]:
            cursor.execute('''
                SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada
                FROM ordenes_fabricacion of
                WHERE of.proyecto_id = %s AND of.estado != 'entregado'
                ORDER BY of.created_at ASC
            ''', (orden['id'],))
            ordenes_fabricacion = cursor.fetchall()
        else:
            ordenes_fabricacion = []

        # Keep dictionary structure but add ordenes_fabricacion as a new attribute
        orden_extended = dict(orden)
        orden_extended['ordenes_fabricacion'] = []

        for fab in ordenes_fabricacion:
            fab_dict = {
                'id': fab['id'], 'codigo_pedido': fab['codigo_orden'], 'nombre': fab['tipo_orden'],
                'estado': fab['estado'], 'fecha_entrega_estimada': fab['fecha_entrega_estimada']
            }
            orden_extended['ordenes_fabricacion'].append(fab_dict)

        ordenes_proceso.append(orden_extended)

    # Órdenes Terminadas
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.prioridad, p.fecha_entrega_real
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('entregado', 'completado')
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.prioridad, p.fecha_entrega_real
        ORDER BY p.fecha_entrega_real DESC
    ''')
    ordenes_terminadas = cursor.fetchall()

    conn.close()

    return render_template('dashboard.html',
                           ordenes_pendientes=ordenes_pendientes,
                           ordenes_proceso=ordenes_proceso,
                           ordenes_terminadas=ordenes_terminadas)


@app.route('/clientes')
@login_required
def clientes():
    """Gestión de clientes y proyectos"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener clientes con información de proyectos
    cursor.execute('''
        SELECT c.id, c.nombre, c.rut, c.email, c.telefono, c.direccion,
               c.ciudad, c.region, c.contacto_principal, c.observaciones,
               COUNT(p.id) as total_proyectos
        FROM clientes c
        LEFT JOIN proyectos p ON c.id = p.cliente_id
        WHERE c.activo = TRUE
        GROUP BY c.id, c.nombre, c.rut, c.email, c.telefono, c.direccion,
                 c.ciudad, c.region, c.contacto_principal, c.observaciones
        ORDER BY c.nombre ASC
    ''')
    clientes_raw = cursor.fetchall()

    clientes_con_proyectos = []
    for cliente in clientes_raw:
        cliente_info = dict(cliente)
        cliente_info['proyectos'] = []

        # Obtener proyectos del cliente
        cursor.execute('''
            SELECT p.id, p.codigo, p.nombre, p.descripcion, p.estado,
                   p.estado_proyecto, p.fecha_inicio, p.monto_neto,
                   p.monto_neto_instalacion, u.nombre as diseñador_nombre,
                   p.prioridad, p.diseñador_id, p.observaciones, p.archivado
            FROM proyectos p
            LEFT JOIN usuarios u ON p.diseñador_id = u.id
            WHERE p.cliente_id = %s
            ORDER BY
                CASE p.estado_proyecto
                    WHEN 'pendiente_presupuesto' THEN 1
                    WHEN 'presupuestado' THEN 2
                    WHEN 'adjudicado' THEN 3
                    ELSE 4
                END,
                p.created_at DESC
        ''', (cliente_info['id'],))

        proyectos = cursor.fetchall()
        for proyecto in proyectos:
            proyecto_dict = dict(proyecto)
            # Handle potential None values for fields that might be null
            proyecto_dict['estado_proyecto'] = proyecto_dict.get('estado_proyecto') or 'pendiente_presupuesto'
            proyecto_dict['prioridad'] = proyecto_dict.get('prioridad') or 'media'
            proyecto_dict['archivado'] = proyecto_dict.get('archivado') or False

            cliente_info['proyectos'].append(proyecto_dict)

        clientes_con_proyectos.append(cliente_info)

    # Obtener clientes disponibles para nuevo proyecto
    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes_disponibles = cursor.fetchall()

    # Obtener diseñadores disponibles
    cursor.execute('SELECT id, nombre FROM usuarios WHERE rol = %s AND activo = TRUE ORDER BY nombre ASC', ('diseñador',))
    diseñadores_disponibles = cursor.fetchall()

    conn.close()

    return render_template('clientes.html',
                         clientes_con_proyectos=clientes_con_proyectos,
                         clientes_disponibles=clientes_disponibles,
                         diseñadores_disponibles=diseñadores_disponibles)


@app.route('/nuevo_cliente', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def nuevo_cliente():
    """Crear nuevo cliente"""
    try:
        nombre = request.form['nombre']
        rut = request.form.get('rut', '').strip() or None
        email = request.form.get('email', '').strip() or None
        telefono = request.form.get('telefono', '').strip() or None
        direccion = request.form.get('direccion', '').strip() or None
        ciudad = request.form.get('ciudad', '').strip() or None
        region = request.form.get('region', '').strip() or None
        contacto_principal = request.form.get('contacto_principal', '').strip() or None
        observaciones = request.form.get('observaciones', '').strip() or None

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO clientes (
                nombre, rut, email, telefono, direccion, ciudad, region,
                contacto_principal, observaciones, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (nombre, rut, email, telefono, direccion, ciudad, region,
              contacto_principal, observaciones, True))

        conn.commit()
        conn.close()

        flash('Cliente creado exitosamente', 'success')

    except psycopg2.errors.UniqueViolation as e:
        if 'rut' in str(e).lower():
            flash('Ya existe un cliente con ese RUT', 'error')
        elif 'email' in str(e).lower():
            flash('Ya existe un cliente con ese email', 'error')
        else:
            flash('Error al crear cliente: datos duplicados', 'error')
    except Exception as e:
        flash(f'Error al crear cliente: {str(e)}', 'error')

    return redirect(url_for('clientes'))


@app.route('/editar_cliente', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def editar_cliente():
    """Editar cliente existente"""
    try:
        cliente_id = request.form['cliente_id']
        nombre = request.form['nombre']
        rut = request.form.get('rut', '').strip() or None
        email = request.form.get('email', '').strip() or None
        telefono = request.form.get('telefono', '').strip() or None
        direccion = request.form.get('direccion', '').strip() or None
        ciudad = request.form.get('ciudad', '').strip() or None
        region = request.form.get('region', '').strip() or None
        contacto_principal = request.form.get('contacto_principal', '').strip() or None
        observaciones = request.form.get('observaciones', '').strip() or None

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE clientes SET
                nombre = %s, rut = %s, email = %s, telefono = %s, direccion = %s,
                ciudad = %s, region = %s, contacto_principal = %s, observaciones = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (nombre, rut, email, telefono, direccion, ciudad, region,
              contacto_principal, observaciones, cliente_id))

        conn.commit()
        conn.close()

        flash('Cliente actualizado exitosamente', 'success')

    except psycopg2.errors.UniqueViolation as e:
        if 'rut' in str(e).lower():
            flash('Ya existe un cliente con ese RUT', 'error')
        elif 'email' in str(e).lower():
            flash('Ya existe un cliente con ese email', 'error')
        else:
            flash('Error al actualizar cliente: datos duplicados', 'error')
    except Exception as e:
        flash(f'Error al actualizar cliente: {str(e)}', 'error')

    return redirect(url_for('clientes'))


@app.route('/eliminar_cliente/<int:cliente_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def eliminar_cliente(cliente_id):
    """Eliminar cliente (solo si no tiene proyectos)"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar si tiene proyectos
        cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s', (cliente_id,))
        proyectos_count = cursor.fetchone()['count']

        if proyectos_count > 0:
            return jsonify({
                'success': False,
                'message': f'No se puede eliminar el cliente porque tiene {proyectos_count} proyecto(s) asociado(s)'
            })

        # Eliminar cliente
        cursor.execute('DELETE FROM clientes WHERE id = %s', (cliente_id,))

        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Cliente eliminado exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar cliente: {str(e)}'})
    finally:
        conn.close()


@app.route('/ordenes_compra')
@login_required
def ordenes_compra():
    """Vista principal de órdenes de compra organizadas por estado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Órdenes de compra pendientes (proyectos con categorías asignadas, no archivados)
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.estado, p.prioridad,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('en_desarrollo') AND p.archivado = FALSE
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.estado, p.prioridad
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_pendientes_raw = cursor.fetchall()

    # Órdenes en Proceso - Solo proyectos que tienen categorías asignadas, no archivados
    cursor.execute('''
        SELECT DISTINCT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.prioridad,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa')
        AND p.archivado = FALSE
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.prioridad
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_proceso_raw = cursor.fetchall()

    # Órdenes Terminadas - Solo proyectos que tienen categorías asignadas, no archivados
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.prioridad, p.fecha_entrega_real
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado IN ('entregado', 'completado') AND p.archivado = FALSE
        GROUP BY p.id, p.codigo, p.nombre, c.nombre, p.fecha_entrega,
                 p.descripcion, p.prioridad, p.fecha_entrega_real
        ORDER BY p.fecha_entrega_real DESC
    ''')
    ordenes_terminadas_raw = cursor.fetchall()

    # Función para obtener categorías de una orden
    def obtener_categorias_orden(proyecto_id):
        cursor.execute('''
            SELECT cat.nombre, COALESCE(subcat.nombre, '') as subcategoria_nombre
            FROM proyecto_categorias pc
            JOIN categorias_producto cat ON pc.categoria_id = cat.id
            LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
            WHERE pc.proyecto_id = %s
        ''', (proyecto_id,))
        categorias = []
        for row in cursor.fetchall():
            cat_nombre = row['nombre']
            subcat_nombre = row['subcategoria_nombre']
            categoria_texto = cat_nombre
            if subcat_nombre:
                categoria_texto += f" - {subcat_nombre}"
            categorias.append(categoria_texto)
        return categorias

    # Función para obtener órdenes de fabricación de una orden
    def obtener_ordenes_fabricacion(proyecto_id):
        # Check if ordenes_fabricacion table exists
        cursor.execute('''
            SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ordenes_fabricacion')
        ''')
        if cursor.fetchone()[0]:
            cursor.execute('''
                SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada
                FROM ordenes_fabricacion of
                WHERE of.proyecto_id = %s AND of.estado != 'entregado'
                ORDER BY of.created_at ASC
            ''', (proyecto_id,))
            ordenes_fab = []
            for fab in cursor.fetchall():
                fab_dict = {
                    'id': fab['id'], 'codigo_pedido': fab['codigo_orden'], 'nombre': fab['tipo_orden'],
                    'estado': fab['estado'], 'fecha_entrega_estimada': fab['fecha_entrega_estimada']
                }
                ordenes_fab.append(fab_dict)
            return ordenes_fab
        else:
            return []

    # Procesar órdenes pendientes
    ordenes_pendientes = []
    for orden in ordenes_pendientes_raw:
        dias_restantes = None
        if orden['dias_restantes'] is not None:
            try:
                dias_restantes = int(orden['dias_restantes'])
            except (ValueError, TypeError):
                dias_restantes = None

        orden_dict = dict(orden)
        orden_dict['dias_restantes'] = dias_restantes
        orden_dict['categorias'] = obtener_categorias_orden(orden['id'])
        ordenes_pendientes.append(orden_dict)

    # Procesar órdenes en proceso
    ordenes_proceso = []
    for orden in ordenes_proceso_raw:
        dias_restantes = None
        if orden['dias_restantes'] is not None:
            try:
                dias_restantes = int(orden['dias_restantes'])
            except (ValueError, TypeError):
                dias_restantes = None

        orden_dict = dict(orden)
        orden_dict['dias_restantes'] = dias_restantes
        orden_dict['categorias'] = obtener_categorias_orden(orden['id'])
        orden_dict['ordenes_fabricacion'] = obtener_ordenes_fabricacion(orden['id'])
        ordenes_proceso.append(orden_dict)

    # Procesar órdenes terminadas
    ordenes_terminadas = []
    for orden in ordenes_terminadas_raw:
        orden_dict = dict(orden)
        ordenes_terminadas.append(orden_dict)

    conn.close()

    return render_template('ordenes_compra.html',
                           ordenes_pendientes=ordenes_pendientes,
                           ordenes_proceso=ordenes_proceso,
                           ordenes_terminadas=ordenes_terminadas)


@app.route('/orden_compra/<int:orden_id>')
@login_required
def orden_compra_detalle(orden_id):
    """Detalle de una orden de compra específica"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener datos de la orden
    cursor.execute('''
        SELECT p.*, c.nombre as cliente_nombre, c.email as cliente_email,
               c.telefono as cliente_telefono, c.contacto_principal
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.id = %s
    ''', (orden_id,))
    orden = cursor.fetchone()

    if not orden:
        flash('Orden de compra no encontrada', 'error')
        return redirect(url_for('ordenes_compra'))

    # Obtener categorías asociadas
    cursor.execute('''
        SELECT cat.nombre, subcat.nombre
        FROM proyecto_categorias pc
        JOIN categorias_producto cat ON pc.categoria_id = cat.id
        LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
        WHERE pc.proyecto_id = %s
    ''', (orden_id,))
    categorias = cursor.fetchall()

    # Obtener órdenes de fabricación si la tabla existe
    cursor.execute('''
        SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ordenes_fabricacion')
    ''')
    if cursor.fetchone()[0]:
        cursor.execute('''
            SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada,
                   of.cantidad_tableros, of.observaciones, of.created_at, of.updated_at
            FROM ordenes_fabricacion of
            WHERE of.proyecto_id = %s
            ORDER BY of.created_at ASC
        ''', (orden_id,))
        ordenes_fabricacion = cursor.fetchall()
    else:
        ordenes_fabricacion = []

    conn.close()

    return render_template('orden_compra_detalle.html',
                           orden=orden,
                           categorias=categorias,
                           ordenes_fabricacion=ordenes_fabricacion)


@app.route('/proyecto/<int:proyecto_id>')
@login_required
def proyecto_detalle(proyecto_id):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Datos del proyecto con información del cliente
    cursor.execute(
        '''
        SELECT p.*, u.nombre as diseñador, c.nombre as cliente_nombre
        FROM proyectos p
        LEFT JOIN usuarios u ON p.diseñador_id = u.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.id = %s
    ''', (proyecto_id, ))
    proyecto = cursor.fetchone()

    conn.close()

    if not proyecto:
        flash('Proyecto no encontrado', 'error')
        return redirect(url_for('clientes'))

    return render_template('proyecto_detalle.html',
                           proyecto=proyecto)


@app.route('/nuevo_proyecto', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nuevo_proyecto():
    """Crear nuevo proyecto con nuevos campos de estado"""
    try:
        nombre = request.form['nombre']
        cliente_id = request.form['cliente_id']
        descripcion = request.form.get('descripcion', '').strip() or None
        estado_proyecto = request.form.get('estado_proyecto', 'pendiente_presupuesto')
        fecha_estimada_inicio = request.form.get('fecha_estimada_inicio') or None
        diseñador_id = request.form.get('diseñador_id') or None
        observaciones = request.form.get('observaciones', '').strip() or None

        # Montos según el estado del proyecto
        monto_neto_provision = None
        monto_neto_instalacion = None

        if estado_proyecto in ['presupuestado', 'adjudicado']:
            monto_provision = request.form.get('monto_neto_provision')
            if monto_provision:
                try:
                    monto_neto_provision = float(monto_provision)
                except ValueError:
                    pass

            monto_instalacion = request.form.get('monto_neto_instalacion')
            if monto_instalacion:
                try:
                    monto_neto_instalacion = float(monto_instalacion)
                except ValueError:
                    pass

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Verificar que el cliente existe
        cursor.execute('SELECT id FROM clientes WHERE id = %s AND activo = TRUE', (cliente_id,))
        if not cursor.fetchone():
            flash('Cliente no válido', 'error')
            return redirect(url_for('clientes'))

        # Obtener nombre del cliente para generar código
        cursor.execute('SELECT nombre FROM clientes WHERE id = %s', (cliente_id,))
        cliente_info = cursor.fetchone()
        cliente_nombre = cliente_info['nombre'] if cliente_info else 'CLIENTE'

        # Limpiar nombre del cliente para código (solo letras y números, máximo 8 caracteres)
        cliente_codigo = ''.join(c.upper() for c in cliente_nombre if c.isalnum())[:8]

        # Generar número secuencial para este cliente
        cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s', (cliente_id,))
        proyecto_numero = cursor.fetchone()['count'] + 1
        codigo_proyecto = f"{cliente_codigo}-{proyecto_numero:03d}"

        # Crear proyecto con los nuevos campos (sin categorías, por lo tanto no aparecerá como orden de compra)
        cursor.execute('''
            INSERT INTO proyectos (
                codigo, nombre, cliente_id, descripcion, estado_proyecto, estado,
                fecha_estimada_inicio, diseñador_id, monto_neto_provision,
                monto_neto_instalacion, observaciones, fecha_inicio
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (codigo_proyecto, nombre, cliente_id, descripcion, estado_proyecto, 'proyecto_simple',
              fecha_estimada_inicio, diseñador_id, monto_neto_provision,
              monto_neto_instalacion, observaciones, datetime.now().date()))

        proyecto_id = cursor.lastrowid

        # Los proyectos creados aquí NO tienen categorías asignadas, por lo tanto no aparecerán
        # en "Órdenes de Compra". Solo se crean como proyectos simples sin flujo de producción automático.

        conn.commit()
        conn.close()

        flash(f'Proyecto {codigo_proyecto} creado exitosamente', 'success')
        return redirect(url_for('clientes'))

    except Exception as e:
        flash(f'Error al crear proyecto: {str(e)}', 'error')
        return redirect(url_for('clientes'))


@app.route('/editar_proyecto', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def editar_proyecto():
    """Editar proyecto existente"""
    try:
        proyecto_id = request.form['proyecto_id']
        codigo = request.form['codigo']
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion', '').strip() or None
        prioridad = request.form.get('prioridad', 'media')
        fecha_entrega = request.form.get('fecha_entrega') or None
        presupuesto = request.form.get('presupuesto')

        # Convertir presupuesto a float si se proporciona
        if presupuesto:
            try:
                presupuesto = float(presupuesto)
            except ValueError:
                presupuesto = None

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Actualizar proyecto
        cursor.execute('''
            UPDATE proyectos SET
                nombre = %s, descripcion = %s, prioridad = %s,
                fecha_entrega = %s, presupuesto = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (nombre, descripcion, prioridad, fecha_entrega, presupuesto, proyecto_id))

        conn.commit()
        conn.close()

        flash('Proyecto actualizado exitosamente', 'success')

    except Exception as e:
        flash(f'Error al actualizar proyecto: {str(e)}', 'error')

    return redirect(url_for('clientes'))


@app.route('/editar_orden_compra', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def editar_orden_compra():
    """Editar orden de compra existente"""
    try:
        proyecto_id = request.form['proyecto_id']
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion', '').strip() or None
        prioridad = request.form.get('prioridad', 'media')
        fecha_entrega = request.form.get('fecha_entrega') or None
        monto_neto = request.form.get('monto_neto')
        observaciones = request.form.get('observaciones', '').strip() or None

        # Convertir monto a float si se proporciona
        if monto_neto:
            try:
                monto_neto = float(monto_neto)
            except ValueError:
                monto_neto = None

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Actualizar orden de compra
        cursor.execute('''
            UPDATE proyectos SET
                nombre = %s, descripcion = %s, prioridad = %s,
                fecha_entrega = %s, monto_neto = %s, observaciones = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (nombre, descripcion, prioridad, fecha_entrega, monto_neto, observaciones, proyecto_id))

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('proyectos', %s, 'UPDATE', %s, %s)
        ''', (proyecto_id, session['user_id'],
              json.dumps({
                  'accion': 'editar_orden_compra',
                  'nombre': nombre,
                  'editado_por': session['user_name']
              })))

        conn.commit()
        conn.close()

        flash('Orden de compra actualizada exitosamente', 'success')

    except Exception as e:
        flash(f'Error al actualizar orden de compra: {str(e)}', 'error')

    return redirect(url_for('ordenes_compra'))


@app.route('/nueva_orden_compra', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nueva_orden_compra():
    """Crear nueva orden de compra con categorías"""
    try:
        # Obtener datos del formulario
        tipo_adjudicacion = request.form.get('tipo_adjudicacion', 'orden_compra')
        numero_oc = request.form['numero_oc']
        cliente_id = request.form.get('cliente_id')
        nuevo_cliente_nombre = request.form.get('nuevo_cliente_nombre')
        proyecto_existente_id = request.form.get('proyecto_existente_id')
        nombre_proyecto = request.form.get('nombre_proyecto')
        descripcion = request.form.get('descripcion', '').strip() or None
        prioridad = request.form.get('prioridad', 'media')
        fecha_entrega_general = request.form.get('fecha_entrega_general')
        fecha_entrega_oc = request.form.get('fecha_entrega_oc')
        monto = request.form.get('monto')
        # Obtener categorías del formulario
        try:
            categorias_json = request.form.get('categorias_selected', '[]')
            subcategorias_json = request.form.get('subcategorias_selected', '[]')
            categorias_selected = json.loads(categorias_json) if categorias_json else []
            subcategorias_selected = json.loads(subcategorias_json) if subcategorias_json else []
        except (json.JSONDecodeError, TypeError):
            # Fallback: intentar obtener como lista directa
            categorias_selected = request.form.getlist('categoria_ids[]')
            subcategorias_selected = request.form.getlist('subcategoria_ids[]')

        # Campos específicos para orden de compra
        fecha_entrega_estimada_cliente = request.form.get('fecha_entrega_estimada_cliente')
        monto_neto_provision = request.form.get('monto_neto_provision')

        # Campos específicos para contrato
        detalle_entregas = request.form.getlist('detalle_entregas[]')
        fechas_entrega = request.form.getlist('fechas_entrega[]')

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Manejar cliente nuevo o existente
        if cliente_id == 'nuevo' and nuevo_cliente_nombre:
            cursor.execute('''
                INSERT INTO clientes (nombre, activo) VALUES (%s, %s) RETURNING id
            ''', (nuevo_cliente_nombre, True))
            cliente_id = cursor.fetchone()['id']
        elif not cliente_id:
            flash('Debe seleccionar un cliente o crear uno nuevo', 'error')
            return redirect(url_for('dashboard'))

        # Verificar que el cliente existe
        cursor.execute('SELECT nombre FROM clientes WHERE id = %s AND activo = TRUE', (cliente_id,))
        cliente_info = cursor.fetchone()
        if not cliente_info:
            flash('Cliente no válido', 'error')
            return redirect(url_for('dashboard'))

        cliente_nombre = cliente_info['nombre']

        # Generar código del proyecto
        cliente_codigo = ''.join(c.upper() for c in cliente_nombre if c.isalnum())[:8]
        cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s', (cliente_id,))
        proyecto_numero = cursor.fetchone()['count'] + 1
        codigo_proyecto = f"{cliente_codigo}-{proyecto_numero:03d}"

        # Determinar si usar proyecto existente o crear nuevo
        if proyecto_existente_id and proyecto_existente_id != 'nuevo':
            # Usar proyecto existente
            cursor.execute('SELECT id, codigo, nombre FROM proyectos WHERE id = %s AND cliente_id = %s',
                         (proyecto_existente_id, cliente_id))
            proyecto_info = cursor.fetchone()
            if not proyecto_info:
                flash('Proyecto no válido para el cliente seleccionado', 'error')
                return redirect(url_for('ordenes_compra'))

            proyecto_id = proyecto_info['id']
            codigo_proyecto = proyecto_info['codigo']

            # Actualizar proyecto con información de la orden/contrato
            observaciones_actuales = f"Número OC/Contrato: {numero_oc}"
            if descripcion:
                observaciones_actuales += f"\nDescripción: {descripcion}"

            cursor.execute('''
                UPDATE proyectos SET
                    adjudicacion_tipo = %s, estado = 'en_desarrollo', prioridad = %s,
                    fecha_entrega = %s, observaciones = COALESCE(observaciones, '') || CHR(10) || %s
                WHERE id = %s
            ''', (tipo_adjudicacion, prioridad,
                  fecha_entrega_general or fecha_entrega_oc or None,
                  observaciones_actuales, proyecto_id))
        else:
            # Crear nuevo proyecto
            if not nombre_proyecto:
                flash('Debe especificar un nombre para el nuevo proyecto', 'error')
                return redirect(url_for('ordenes_compra'))

            # Generar código del proyecto
            cliente_codigo = ''.join(c.upper() for c in cliente_nombre if c.isalnum())[:8]
            cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s', (cliente_id,))
            proyecto_numero = cursor.fetchone()['count'] + 1
            codigo_proyecto = f"{cliente_codigo}-{proyecto_numero:03d}"

            # Convertir monto si se proporciona
            monto_num = None
            if monto:
                try:
                    monto_num = float(monto)
                except ValueError:
                    pass

            monto_provision_num = None
            if monto_neto_provision:
                try:
                    monto_provision_num = float(monto_neto_provision)
                except ValueError:
                    pass

            # Crear proyecto
            cursor.execute('''
                INSERT INTO proyectos (
                    codigo, nombre, cliente_id, descripcion, adjudicacion_tipo,
                    estado, prioridad, fecha_inicio, fecha_entrega,
                    monto_neto, monto_neto_provision, observaciones
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (codigo_proyecto, nombre_proyecto, cliente_id, descripcion, tipo_adjudicacion,
                  'en_desarrollo', prioridad, datetime.now().date(),
                  fecha_entrega_general or fecha_entrega_oc or None,
                  monto_num, monto_provision_num, f"Número OC/Contrato: {numero_oc}"))
            proyecto_id = cursor.fetchone()['id']

        # Agregar categorías al proyecto
        if categorias_selected:
            try:
                for i, categoria_id in enumerate(categorias_selected):
                    if categoria_id:  # Solo si hay categoría seleccionada
                        subcategoria_id = subcategorias_selected[i] if i < len(subcategorias_selected) and subcategorias_selected[i] else None
                        cursor.execute('''
                            INSERT INTO proyecto_categorias (proyecto_id, categoria_id, subcategoria_id)
                            VALUES (%s, %s, %s)
                        ''', (proyecto_id, categoria_id, subcategoria_id))
            except Exception as e:
                flash(f'Error procesando categorías: {str(e)}', 'error')
                return redirect(url_for('ordenes_compra'))

        # Si es contrato, agregar entregas programadas
        if tipo_adjudicacion == 'contrato' and detalle_entregas:
            for i, detalle in enumerate(detalle_entregas):
                if detalle and i < len(fechas_entrega) and fechas_entrega[i]:
                    cursor.execute('''
                        INSERT INTO entregas_contrato (proyecto_id, detalle, fecha_entrega, estado)
                        VALUES (%s, %s, %s, %s)
                    ''', (proyecto_id, detalle, fechas_entrega[i], 'programada'))

        conn.commit()
        conn.close()

        flash(f'{"Contrato" if tipo_adjudicacion == "contrato" else "Orden de compra"} {codigo_proyecto} creada exitosamente', 'success')
        return redirect(url_for('ordenes_compra'))

    except Exception as e:
        flash(f'Error al crear orden: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/eliminar_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def eliminar_proyecto(proyecto_id):
    """Eliminar proyecto (solo administradores)"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que el proyecto existe y obtener información
        cursor.execute('SELECT codigo, nombre, estado FROM proyectos WHERE id = %s', (proyecto_id,))
        proyecto = cursor.fetchone()

        if not proyecto:
            return jsonify({'success': False, 'message': 'Proyecto no encontrado'})

        codigo_proyecto, nombre_proyecto, estado_proyecto = proyecto['codigo'], proyecto['nombre'], proyecto['estado']

        # Verificar si tiene despachos entregados (solo estos no se pueden eliminar)
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE proyecto_id = %s AND estado = %s', (proyecto_id, 'entregado'))
        despachos_entregados = cursor.fetchone()['count']

        if despachos_entregados > 0:
            return jsonify({
                'success': False,
                'message': f'No se puede eliminar el proyecto porque tiene {despachos_entregados} despacho(s) entregado(s). Solo se pueden eliminar proyectos sin despachos completamente entregados.'
            })

        # Eliminar todas las dependencias del proyecto en orden

        # 1. Eliminar evidencias asociadas a tareas del proyecto
        cursor.execute('DELETE FROM evidencias WHERE tarea_id IN (SELECT id FROM tareas WHERE proyecto_id = %s)', (proyecto_id,))
        cursor.execute('DELETE FROM evidencias WHERE proyecto_id = %s', (proyecto_id,)) # This might be redundant if tarea_id is always populated

        # 2. Eliminar tareas del proyecto
        cursor.execute('DELETE FROM tareas WHERE proyecto_id = %s', (proyecto_id,))

        # 3. Eliminar categorías de órdenes de fabricación
        cursor.execute('''
            DELETE FROM orden_fabricacion_categorias
            WHERE orden_fabricacion_id IN (SELECT id FROM ordenes_fabricacion WHERE proyecto_id = %s)
        ''', (proyecto_id,))

        # 4. Eliminar órdenes de fabricación
        cursor.execute('DELETE FROM ordenes_fabricacion WHERE proyecto_id = %s', (proyecto_id,))

        # 6. Eliminar entregas de contrato
        cursor.execute('DELETE FROM entregas_contrato WHERE proyecto_id = %s', (proyecto_id,))

        # 7. Eliminar despachos programados (no críticos)
        cursor.execute('DELETE FROM despachos WHERE proyecto_id = %s AND estado NOT IN (%s, %s)', (proyecto_id, 'en_transito', 'entregado'))

        # 8. Eliminar documentos del proyecto
        cursor.execute('DELETE FROM documentos_proyecto WHERE proyecto_id = %s', (proyecto_id,))

        # 9. Eliminar categorías del proyecto
        cursor.execute('DELETE FROM proyecto_categorias WHERE proyecto_id = %s', (proyecto_id,))

        # 10. Eliminar recordatorios del proyecto
        cursor.execute('DELETE FROM recordatorios WHERE tipo = %s AND referencia_id = %s', ('proyecto', proyecto_id))

        # 11. Eliminar incidencias del proyecto
        cursor.execute('DELETE FROM incidencias WHERE proyecto_id = %s', (proyecto_id,))

        # Finalmente eliminar el proyecto
        cursor.execute('DELETE FROM proyectos WHERE id = %s', (proyecto_id,))

        if cursor.rowcount > 0:
            # Registrar en auditoría
            cursor.execute('''
                INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
                VALUES ('proyectos', %s, 'DELETE', %s, %s)
            ''', (proyecto_id, session['user_id'],
                  json.dumps({
                      'accion': 'eliminar_proyecto',
                      'codigo': codigo_proyecto,
                      'nombre': nombre_proyecto,
                      'eliminado_por': session['user_name']
                  })))

            conn.commit()
            return jsonify({'success': True, 'message': f'Proyecto {codigo_proyecto} eliminado exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'No se pudo eliminar el proyecto'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar proyecto: {str(e)}'})
    finally:
        conn.close()


@app.route('/archivar_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def archivar_proyecto(proyecto_id):
    """Archivar proyecto terminado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que el proyecto existe y está terminado
        cursor.execute('SELECT codigo, nombre, estado FROM proyectos WHERE id = %s', (proyecto_id,))
        proyecto = cursor.fetchone()

        if not proyecto:
            return jsonify({'success': False, 'message': 'Proyecto no encontrado'})

        codigo_proyecto, nombre_proyecto, estado_proyecto = proyecto['codigo'], proyecto['nombre'], proyecto['estado']

        if estado_proyecto not in ['entregado', 'completado']:
            return jsonify({'success': False, 'message': 'Solo se pueden archivar proyectos terminados'})

        # Archivar el proyecto
        cursor.execute('UPDATE proyectos SET archivado = TRUE WHERE id = %s', (proyecto_id,))

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('proyectos', %s, 'ARCHIVE', %s, %s)
        ''', (proyecto_id, session['user_id'],
              json.dumps({
                  'accion': 'archivar_proyecto',
                  'codigo': codigo_proyecto,
                  'nombre': nombre_proyecto,
                  'archivado_por': session['user_name']
              })))

        conn.commit()
        return jsonify({'success': True, 'message': f'Proyecto {codigo_proyecto} archivado exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al archivar proyecto: {str(e)}'})
    finally:
        conn.close()


@app.route('/desarchivar_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def desarchivar_proyecto(proyecto_id):
    """Desarchivar proyecto"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que el proyecto existe
        cursor.execute('SELECT codigo, nombre FROM proyectos WHERE id = %s', (proyecto_id,))
        proyecto = cursor.fetchone()

        if not proyecto:
            return jsonify({'success': False, 'message': 'Proyecto no encontrado'})

        codigo_proyecto, nombre_proyecto = proyecto['codigo'], proyecto['nombre']

        # Desarchivar el proyecto
        cursor.execute('UPDATE proyectos SET archivado = FALSE WHERE id = %s', (proyecto_id,))

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('proyectos', %s, 'UNARCHIVE', %s, %s)
        ''', (proyecto_id, session['user_id'],
              json.dumps({
                  'accion': 'desarchivar_proyecto',
                  'codigo': codigo_proyecto,
                  'nombre': nombre_proyecto,
                  'desarchivado_por': session['user_name']
              })))

        conn.commit()
        return jsonify({'success': True, 'message': f'Proyecto {codigo_proyecto} desarchivado exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al desarchivar proyecto: {str(e)}'})
    finally:
        conn.close()


@app.route('/gestion_pedidos')
@login_required
def gestion_pedidos():
    """Vista de gestión de pedidos por estado (reemplaza el sistema anterior)"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener órdenes de compra en diferentes estados
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega,
               p.descripcion, p.estado, p.prioridad,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado NOT IN ('entregado', 'cancelado') AND p.archivado = FALSE
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    pedidos = cursor.fetchall()

    # Agrupar por estado
    pedidos_por_estado = {
        'en_desarrollo': {'nombre': 'En Desarrollo', 'pedidos': [], 'rol_responsable': 'diseñador'},
        'aprobado_produccion': {'nombre': 'Aprobado para Producción', 'pedidos': [], 'rol_responsable': 'operación'},
        'seccionado': {'nombre': 'En Seccionado', 'pedidos': [], 'rol_responsable': 'operación'},
        'enchapado': {'nombre': 'En Enchapado', 'pedidos': [], 'rol_responsable': 'operación'},
        'mecanizado': {'nombre': 'En Mecanizado', 'pedidos': [], 'rol_responsable': 'operación'},
        'produccion_completa': {'nombre': 'Producción Completa', 'pedidos': [], 'rol_responsable': 'embalaje'},
        'embalando': {'nombre': 'En Embalaje', 'pedidos': [], 'rol_responsable': 'embalaje'},
        'listo_despacho': {'nombre': 'Listo para Despacho', 'pedidos': [], 'rol_responsable': 'despacho'},
    }

    for pedido in pedidos:
        estado = pedido['estado']  # estado field
        if estado in pedidos_por_estado:
            pedidos_por_estado[estado]['pedidos'].append(pedido)

    conn.close()
    return render_template('gestion_pedidos.html', pedidos_por_estado=pedidos_por_estado)

@app.route('/tareas')
@login_required
def tareas():
    """Redirigir al nuevo sistema de gestión de pedidos por estado"""
    return redirect(url_for('gestion_pedidos'))


@app.route('/tarea/<int:tarea_id>')
@login_required
def tarea_detalle(tarea_id):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute(
        '''
        SELECT t.*, p.nombre as proyecto, u.nombre as asignado
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.id = %s
    ''', (tarea_id, ))
    tarea = cursor.fetchone()

    cursor.execute(
        '''
        SELECT * FROM evidencias WHERE tarea_id = %s ORDER BY uploaded_at DESC
    ''', (tarea_id, ))
    evidencias = cursor.fetchall()

    conn.close()

    if not tarea:
        flash('Tarea no encontrada', 'error')
        return redirect(url_for('tareas'))

    return render_template('tarea_detalle.html',
                           tarea=tarea,
                           evidencias=evidencias)


@app.route('/completar_tarea/<int:tarea_id>', methods=['POST'])
@login_required
def completar_tarea(tarea_id):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Verificar que el usuario puede completar esta tarea
    cursor.execute(
        '''
        SELECT rol_asignado, usuario_asignado_id FROM tareas WHERE id = %s
    ''', (tarea_id, ))
    tarea = cursor.fetchone()

    if not tarea:
        flash('Tarea no encontrada', 'error')
        return redirect(url_for('tareas'))

    if (tarea['rol_asignado'] != session['user_role'] and tarea['usuario_asignado_id'] != session['user_id']
            and session['user_role'] != 'admin'):
        flash('No tienes permisos para completar esta tarea', 'error')
        return redirect(url_for('tarea_detalle', tarea_id=tarea_id))

    cursor.execute(
        '''
        UPDATE tareas SET estado = 'completada', fecha_completada = %s
        WHERE id = %s
    ''', (datetime.now(), tarea_id))

    conn.commit()
    conn.close()

    flash('Tarea completada exitosamente', 'success')
    return redirect(url_for('tarea_detalle', tarea_id=tarea_id))


@app.route('/usuarios')
@login_required
@role_required(['admin'])
def usuarios():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, nombre, rol, email, created_at FROM usuarios ORDER BY created_at DESC'
    )
    usuarios_list = cursor.fetchall()
    conn.close()

    return render_template('usuarios.html',
                           usuarios=usuarios_list,
                           roles=ROLES)


@app.route('/nuevo_usuario', methods=['POST'])
@login_required
@role_required(['admin'])
def nuevo_usuario():
    username = request.form['username']
    password = request.form['password']
    nombre = request.form['nombre']
    rol = request.form['rol']
    email = request.form['email']

    if rol not in ROLES:
        flash('Rol inválido', 'error')
        return redirect(url_for('usuarios'))

    password_hash = generate_password_hash(password)

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''
            INSERT INTO usuarios (username, password_hash, nombre, rol, email)
            VALUES (%s, %s, %s, %s, %s)
        ''', (username, password_hash, nombre, rol, email))
        conn.commit()
        flash('Usuario creado exitosamente', 'success')
    except psycopg2.errors.UniqueViolation:
        flash('El nombre de usuario o email ya existe', 'error')
    finally:
        conn.close()

    return redirect(url_for('usuarios'))


@app.route('/crear_despacho', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def crear_despacho():
    """
    Crear un despacho flexible con solo cliente, obra y fecha como obligatorios
    """
    try:
        # Campos obligatorios
        cliente_nombre = request.form.get('cliente_nombre', '').strip()
        obra_nombre = request.form.get('obra_nombre', '').strip()
        fecha_despacho = request.form.get('fecha_despacho')

        # Validar campos obligatorios
        if not all([cliente_nombre, obra_nombre, fecha_despacho]):
            flash('Los campos Cliente, Obra y Fecha de Despacho son obligatorios', 'error')
            return redirect(request.referrer or url_for('despachos'))

        # Campos opcionales
        direccion_entrega = request.form.get('direccion_entrega', '').strip()
        contacto_entrega = request.form.get('contacto_entrega', '').strip()
        telefono_contacto = request.form.get('telefono_contacto', '').strip()
        transportista = request.form.get('transportista', '').strip()
        conductor = request.form.get('conductor', '').strip()
        telefono_conductor = request.form.get('telefono_conductor', '').strip()
        vehiculo_patente = request.form.get('vehiculo_patente', '').strip()
        descripcion_productos = request.form.get('descripcion_productos', '').strip()
        cantidad_bultos = request.form.get('cantidad_bultos', '').strip()
        peso_estimado = request.form.get('peso_estimado', '').strip()
        hora_programada = request.form.get('hora_programada', '').strip()
        horario_entrega = request.form.get('horario_entrega', '').strip()
        restricciones = request.form.get('restricciones', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Generar código único para el despacho
        # PostgreSQL uses EXTRACT and TO_CHAR for year and zero-padding
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)')
        despacho_numero = cursor.fetchone()['count'] + 1
        codigo_despacho = f"DESP-{datetime.now().year}-{despacho_numero:04d}"

        # Crear información completa en observaciones
        info_completa = f"CLIENTE: {cliente_nombre}\nOBRA/PROYECTO: {obra_nombre}"

        if descripcion_productos:
            info_completa += f"\nPRODUCTOS: {descripcion_productos}"
        if cantidad_bultos:
            info_completa += f"\nCANTIDAD BULTOS: {cantidad_bultos}"
        if peso_estimado:
            info_completa += f"\nPESO ESTIMADO: {peso_estimado} kg"
        if contacto_entrega:
            info_completa += f"\nCONTACTO ENTREGA: {contacto_entrega}"
        if telefono_contacto:
            info_completa += f"\nTELÉFONO CONTACTO: {telefono_contacto}"
        if hora_programada:
            info_completa += f"\nHora Programada: {hora_programada}"
        if horario_entrega:
            info_completa += f"\nHORARIO ENTREGA: {horario_entrega}"
        if restricciones:
            info_completa += f"\nRESTRICCIONES: {restricciones}"
        if observaciones:
            info_completa += f"\n\nOBSERVACIONES ADICIONALES:\n{observaciones}"

        # Insertar el despacho (sin proyecto_id ya que es entrada manual)
        cursor.execute('''
            INSERT INTO despachos (
                codigo_despacho, transportista, conductor,
                telefono_conductor, vehiculo_patente, direccion_entrega,
                fecha_programada, observaciones, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (codigo_despacho, transportista, conductor,
              telefono_conductor, vehiculo_patente, direccion_entrega,
              fecha_despacho, info_completa, 'programado'))
        despacho_id = cursor.fetchone()['id']

        # Manejar archivos subidos si existen
        for file_key in request.files:
            files = request.files.getlist(file_key)
            for file in files:
                if file and file.filename:
                    file_path = save_uploaded_file(file, 'despachos')
                    if file_path:
                        tipo_archivo = file_key.replace('archivo_', '')
                        cursor.execute('''
                            INSERT INTO despacho_archivos (despacho_id, tipo, nombre_original, ruta_archivo, tamaño)
                            VALUES (%s, %s, %s, %s, %s)
                        ''', (despacho_id, tipo_archivo, file.filename, file_path, len(file.read()) if hasattr(file, 'read') else 0))

        # Crear recordatorios automáticos
        fecha_despacho_dt = datetime.strptime(fecha_despacho, '%Y-%m-%d').date()

        # Recordatorio 5 días antes
        fecha_recordatorio = fecha_despacho_dt - timedelta(days=5)
        cursor.execute('SELECT id FROM areas WHERE nombre = %s LIMIT 1', ('Despacho',))
        area_despacho = cursor.fetchone()
        area_id = area_despacho['id'] if area_despacho else None

        titulo_recordatorio = f"Preparar despacho {codigo_despacho}"
        mensaje_recordatorio = f"Despacho programado para {fecha_despacho}.\nCliente: {cliente_nombre}\nObra: {obra_nombre}"
        if direccion_entrega:
            mensaje_recordatorio += f"\nDirección: {direccion_entrega}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje,
                fecha_recordatorio, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', ('despacho', despacho_id, area_id, titulo_recordatorio,
              mensaje_recordatorio, fecha_recordatorio, True))

        # Recordatorio el día anterior
        fecha_recordatorio_urgente = fecha_despacho_dt - timedelta(days=1)
        titulo_urgente = f"Despacho mañana: {codigo_despacho}"
        mensaje_urgente = f"Despacho programado para mañana ({fecha_despacho}).\nCliente: {cliente_nombre}\nObra: {obra_nombre}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje,
                fecha_recordatorio, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', ('despacho', despacho_id, area_id, titulo_urgente,
              mensaje_urgente, fecha_recordatorio_urgente, True))

        conn.commit()
        conn.close()

        flash(f'Despacho {codigo_despacho} creado exitosamente. Recordatorios automáticos configurados.', 'success')
        return redirect(url_for('despacho_detalle', despacho_id=despacho_id))

    except Exception as e:
        flash(f'Error al crear despacho: {str(e)}', 'error')
        return redirect(request.referrer or url_for('despachos'))


@app.route('/programar_despacho_con_orden', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def programar_despacho_con_orden():
    """
    Programar despacho con orden de producción automática
    """
    try:
        cliente_id = request.form.get('cliente_id')
        proyecto_id = request.form.get('proyecto_id')
        proyecto_nombre = request.form.get('proyecto_nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        presupuesto = request.form.get('presupuesto', '').strip()
        fecha_despacho = request.form.get('fecha_despacho')
        prioridad = request.form.get('prioridad', 'media')
        direccion_entrega = request.form.get('direccion_entrega', '').strip()
        transportista = request.form.get('transportista', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        # Validar campos obligatorios
        if not all([cliente_id, fecha_despacho, direccion_entrega]):
            flash('Cliente, fecha de despacho y dirección son obligatorios', 'error')
            return redirect(request.referrer or url_for('despachos'))

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Verificar que el cliente existe
        cursor.execute('SELECT nombre FROM clientes WHERE id = %s AND activo = TRUE', (cliente_id,))
        cliente = cursor.fetchone()
        if not cliente:
            flash('Cliente no válido', 'error')
            return redirect(request.referrer or url_for('despachos'))

        cliente_nombre = cliente['nombre']

        # Si no se seleccionó proyecto existente, crear uno nuevo
        if not proyecto_id:
            if not proyecto_nombre:
                flash('Debe especificar un nombre para el nuevo proyecto', 'error')
                return redirect(request.referrer or url_for('despachos'))

            # Obtener nombre del cliente para generar código
            cursor.execute('SELECT nombre FROM clientes WHERE id = %s', (cliente_id,))
            cliente_info = cursor.fetchone()
            cliente_nombre = cliente_info['nombre'] if cliente_info else 'CLIENTE'

            # Limpiar nombre del cliente para código (solo letras y números, máximo 8 caracteres)
            cliente_codigo = ''.join(c.upper() for c in cliente_nombre if c.isalnum())[:8]

            # Generar número secuencial para este cliente
            cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s', (cliente_id,))
            proyecto_numero = cursor.fetchone()['count'] + 1
            codigo_proyecto = f"{cliente_codigo}-{proyecto_numero:03d}"

            # Convertir presupuesto si se proporciona
            presupuesto_num = None
            if presupuesto:
                try:
                    presupuesto_num = float(presupuesto)
                except ValueError:
                    pass

            # Crear proyecto
            cursor.execute('''
                INSERT INTO proyectos (
                    codigo, nombre, cliente_id, descripcion, estado, prioridad,
                    fecha_inicio, fecha_entrega, presupuesto
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (codigo_proyecto, proyecto_nombre, cliente_id, descripcion, 'pendiente_fabricacion', prioridad,
                  datetime.now().date(), fecha_despacho, presupuesto_num))
            proyecto_id = cursor.fetchone()['id']

            # Crear tareas automáticas del ciclo de vida de producción
            fecha_inicio = datetime.now().date()
            fecha_despacho_dt = datetime.strptime(fecha_despacho, '%Y-%m-%d').date()
            dias_disponibles = (fecha_despacho_dt - fecha_inicio).days

            # Distribuir las tareas proporcionalmente en el tiempo disponible
            tareas_produccion = [
                ('Diseño y planificación', 'Crear diseño y planificar producción', 'diseñador', 'diseño', 0.15),
                ('Aprobación de diseño', 'Revisar y aprobar diseño para producción', 'general', 'diseño', 0.25),
                ('Seccionado', 'Corte y seccionado de materiales', 'operación', 'fabricación', 0.35),
                ('Enchapado', 'Proceso de enchapado de piezas', 'operación', 'fabricación', 0.55),
                ('Mecanizado', 'Mecanizado y acabado de piezas', 'operación', 'fabricación', 0.75),
                ('Fabricación completa', 'Ensamble y fabricación final', 'operación', 'fabricación', 0.85),
                ('Control de calidad', 'Inspección y control de calidad', 'operación', 'control_calidad', 0.90),
                ('Embalaje', 'Embalaje para despacho', 'embalaje', 'embalaje', 0.95),
                ('Preparación despacho', 'Preparar documentación y coordinar despacho', 'despacho', 'despacho', 1.0)
            ]

            for titulo, descripcion_tarea, rol, tipo, factor_tiempo in tareas_produccion:
                dias_desde_inicio = int(dias_disponibles * factor_tiempo)
                fecha_programada = fecha_inicio + timedelta(days=dias_desde_inicio)

                etapa_fab = None
                if rol == 'operación' and tipo == 'fabricación':
                    if 'Seccionado' in titulo:
                        etapa_fab = 'seccionado'
                    elif 'Enchapado' in titulo:
                        etapa_fab = 'enchapado'
                    elif 'Mecanizado' in titulo:
                        etapa_fab = 'mecanizado'
                    elif 'Fabricación completa' in titulo:
                        etapa_fab = 'fabricacion_completo'

                cursor.execute('''
                    INSERT INTO tareas (
                        proyecto_id, titulo, descripcion, rol_asignado, tipo,
                        fecha_programada, estado, prioridad, etapa_fabricacion
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (proyecto_id, titulo, descripcion_tarea, rol, tipo,
                      fecha_programada, 'pendiente', prioridad, etapa_fab))

        else:
            # Verificar que el proyecto existe y pertenece al cliente
            cursor.execute('''
                SELECT p.nombre, p.codigo FROM proyectos p
                WHERE p.id = %s AND p.cliente_id = %s
            ''', (proyecto_id, cliente_id))
            proyecto_info = cursor.fetchone()
            if not proyecto_info:
                flash('Proyecto no válido para el cliente seleccionado', 'error')
                return redirect(request.referrer or url_for('despachos'))

            proyecto_nombre = proyecto_info['nombre']
            codigo_proyecto = proyecto_info['codigo']

            # Actualizar estado del proyecto a pendiente_fabricacion si no lo está
            cursor.execute('''
                UPDATE proyectos SET estado = %s,
                fecha_entrega = %s, prioridad = %s
                WHERE id = %s
            ''', ('pendiente_fabricacion', fecha_despacho, prioridad, proyecto_id))

        # Crear el despacho
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)')
        despacho_numero = cursor.fetchone()['count'] + 1
        codigo_despacho = f"DESP-{datetime.now().year}-{despacho_numero:04d}"

        observaciones_completas = f"ORDEN DE PRODUCCIÓN AUTOMÁTICA\nCliente: {cliente_nombre}\nProyecto: {proyecto_nombre}"
        if observaciones:
            observaciones_completas += f"\n\nObservaciones: {observaciones}"

        cursor.execute('''
            INSERT INTO despachos (
                proyecto_id, codigo_despacho, transportista, direccion_entrega,
                fecha_programada, observaciones, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (proyecto_id, codigo_despacho, transportista, direccion_entrega,
              fecha_despacho, observaciones_completas, 'programado'))
        despacho_id = cursor.fetchone()['id']

        # Crear recordatorios
        fecha_despacho_dt = datetime.strptime(fecha_despacho, '%Y-%m-%d').date()

        # Recordatorio para iniciar producción (inmediato)
        cursor.execute('SELECT id FROM areas WHERE nombre = %s LIMIT 1', ('Producción',))
        area_produccion = cursor.fetchone()
        area_prod_id = area_produccion['id'] if area_produccion else None

        titulo_produccion = f"Nueva orden de producción: {codigo_proyecto}"
        mensaje_produccion = f"Se ha creado una nueva orden de producción para el proyecto {proyecto_nombre}.\nCliente: {cliente_nombre}\nFecha límite de despacho: {fecha_despacho}\nPrioridad: {prioridad.upper()}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje,
                fecha_recordatorio, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', ('proyecto', proyecto_id, area_prod_id, titulo_produccion,
              mensaje_produccion, datetime.now().date(), True))

        # Recordatorio de despacho 5 días antes
        fecha_recordatorio_despacho = fecha_despacho_dt - timedelta(days=5)
        cursor.execute('SELECT id FROM areas WHERE nombre = %s LIMIT 1', ('Despacho',))
        area_despacho = cursor.fetchone()
        area_desp_id = area_despacho['id'] if area_despacho else None

        titulo_despacho = f"Preparar despacho {codigo_despacho}"
        mensaje_despacho = f"Despacho programado para {fecha_despacho}.\nProyecto: {proyecto_nombre}\nCliente: {cliente_nombre}\nDirección: {direccion_entrega}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje,
                fecha_recordatorio, activo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', ('despacho', despacho_id, area_desp_id, titulo_despacho,
              mensaje_despacho, fecha_recordatorio_despacho, True))

        conn.commit()
        conn.close()

        flash(f'Orden de producción y despacho {codigo_despacho} creados exitosamente. Proyecto {codigo_proyecto} en estado "pendiente de fabricación".', 'success')
        return redirect(url_for('proyecto_detalle', proyecto_id=proyecto_id))

    except Exception as e:
        flash(f'Error al programar despacho con orden: {str(e)}', 'error')
        return redirect(request.referrer or url_for('despachos'))


@app.route('/despachos')
@login_required
@role_required(['admin', 'general', 'despacho'])
def despachos():
    """Ver todos los despachos programados"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.*,
               COALESCE(p.nombre, 'Proyecto Manual') as proyecto_nombre,
               COALESCE(p.codigo, d.codigo_despacho) as proyecto_codigo,
               COALESCE(c.nombre, 'Cliente Manual') as cliente_nombre
        FROM despachos d
        LEFT JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        ORDER BY d.fecha_programada ASC
    ''')
    despachos_list = cursor.fetchall()

    # Obtener clientes disponibles para modal de programar despacho con orden
    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes_disponibles = cursor.fetchall()

    conn.close()

    return render_template('despachos.html', despachos=despachos_list, clientes_disponibles=clientes_disponibles)


@app.route('/despacho/<int:despacho_id>')
@login_required
@role_required(['admin', 'general', 'despacho'])
def despacho_detalle(despacho_id):
    """Ver detalle de un despacho específico"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener datos del despacho
    cursor.execute('''
        SELECT d.*, p.nombre as proyecto_nombre, p.codigo as proyecto_codigo,
               c.nombre as cliente_nombre, c.direccion as cliente_direccion
        FROM despachos d
        LEFT JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE d.id = %s
    ''', (despacho_id,))

    despacho = cursor.fetchone()

    if not despacho:
        flash('Despacho no encontrado', 'error')
        return redirect(url_for('despachos'))

    # Obtener archivos del despacho
    cursor.execute('''
        SELECT * FROM despacho_archivos
        WHERE despacho_id = %s
        ORDER BY created_at DESC
    ''', (despacho_id,))

    archivos = cursor.fetchall()
    conn.close()

    return render_template('despacho_detalle.html', despacho=despacho, archivos=archivos)


@app.route('/editar_despacho/<int:despacho_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def editar_despacho(despacho_id):
    """Editar un despacho existente"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            transportista = request.form.get('transportista', '')
            conductor = request.form.get('conductor', '')
            telefono_conductor = request.form.get('telefono_conductor', '')
            vehiculo_patente = request.form.get('vehiculo_patente', '')
            direccion_entrega = request.form.get('direccion_entrega')
            observaciones = request.form.get('observaciones', '')
            fecha_programada = request.form.get('fecha_programada')

            if not all([direccion_entrega, fecha_programada]):
                flash('Faltan datos obligatorios', 'error')
                return redirect(request.referrer)

            # Actualizar despacho
            cursor.execute('''
                UPDATE despachos SET
                    transportista = %s, conductor = %s, telefono_conductor = %s,
                    vehiculo_patente = %s, direccion_entrega = %s, observaciones = %s,
                    fecha_programada = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (transportista, conductor, telefono_conductor, vehiculo_patente,
                  direccion_entrega, observaciones, fecha_programada, despacho_id))

            # Manejar archivos subidos
            for file_key in request.files:
                file = request.files[file_key]
                if file and file.filename:
                    file_path = save_uploaded_file(file, 'despachos')
                    if file_path:
                        tipo_archivo = file_key.replace('archivo_', '')
                        cursor.execute('''
                            INSERT INTO despacho_archivos (despacho_id, tipo, nombre_original, ruta_archivo)
                            VALUES (%s, %s, %s, %s)
                        ''', (despacho_id, tipo_archivo, file.filename, file_path))

            conn.commit()
            flash('Despacho actualizado exitosamente', 'success')
            return redirect(url_for('despacho_detalle', despacho_id=despacho_id))

        except Exception as e:
            flash(f'Error al actualizar despacho: {str(e)}', 'error')
            return redirect(request.referrer)
        finally:
            conn.close()

    # GET request - mostrar formulario de edición
    cursor.execute('''
        SELECT d.*, p.nombre as proyecto_nombre, p.codigo as proyecto_codigo
        FROM despachos d
        LEFT JOIN proyectos p ON d.proyecto_id = p.id
        WHERE d.id = %s
    ''', (despacho_id,))

    despacho = cursor.fetchone()
    conn.close()

    if not despacho:
        flash('Despacho no encontrado', 'error')
        return redirect(url_for('despachos'))

    return render_template('editar_despacho.html', despacho=despacho)


@app.route('/eliminar_despacho/<int:despacho_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def eliminar_despacho(despacho_id):
    """Eliminar un despacho y sus archivos asociados"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener archivos para eliminarlos del sistema
        cursor.execute('SELECT ruta_archivo FROM despacho_archivos WHERE despacho_id = %s', (despacho_id,))
        archivos = cursor.fetchall()

        # Eliminar archivos del sistema de archivos
        for archivo in archivos:
            delete_file(archivo['ruta_archivo'])

        # Eliminar registros de archivos
        cursor.execute('DELETE FROM despacho_archivos WHERE despacho_id = %s', (despacho_id,))

        # Eliminar recordatorios asociados
        cursor.execute('DELETE FROM recordatorios WHERE tipo = %s AND referencia_id = %s', ('despacho', despacho_id))

        # Eliminar despacho
        cursor.execute('DELETE FROM despachos WHERE id = %s', (despacho_id,))

        conn.commit()
        flash('Despacho eliminado exitosamente', 'success')

    except Exception as e:
        flash(f'Error al eliminar despacho: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('despachos'))


@app.route('/eliminar_archivo_despacho/<int:archivo_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def eliminar_archivo_despacho(archivo_id):
    """Eliminar un archivo específico de un despacho"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener información del archivo
        cursor.execute('SELECT despacho_id, ruta_archivo FROM despacho_archivos WHERE id = %s', (archivo_id,))
        archivo = cursor.fetchone()

        if archivo:
            despacho_id, ruta_archivo = archivo['despacho_id'], archivo['ruta_archivo']

            # Eliminar archivo del sistema
            delete_file(ruta_archivo)

            # Eliminar registro de la base de datos
            cursor.execute('DELETE FROM despacho_archivos WHERE id = %s', (archivo_id,))
            conn.commit()

            flash('Archivo eliminado exitosamente', 'success')
            return redirect(url_for('despacho_detalle', despacho_id=despacho_id))
        else:
            flash('Archivo no encontrado', 'error')

    except Exception as e:
        flash(f'Error al eliminar archivo: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('despachos'))


@app.route('/despacho/<int:despacho_id>/en_transito', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def marcar_despacho_en_transito(despacho_id):
    """Marcar un despacho como en tránsito"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE despachos SET estado = 'en_transito', fecha_despacho = CURRENT_TIMESTAMP
            WHERE id = %s AND estado = 'programado'
        ''', (despacho_id,))

        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Despacho marcado como en tránsito'})
        else:
            return jsonify({'success': False, 'message': 'No se pudo actualizar el despacho'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/despacho/<int:despacho_id>/entregado', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def marcar_despacho_entregado(despacho_id):
    """Marcar un despacho como entregado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE despachos SET estado = 'entregado', fecha_entrega = CURRENT_TIMESTAMP
            WHERE id = %s AND estado = 'en_transito'
        ''', (despacho_id,))

        # También actualizar el proyecto como entregado
        cursor.execute('''
            UPDATE proyectos SET estado = %s, fecha_entrega_real = CURRENT_TIMESTAMP
            WHERE id = (SELECT proyecto_id FROM despachos WHERE id = %s)
        ''', ('entregado', despacho_id))

        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Despacho marcado como entregado'})
        else:
            return jsonify({'success': False, 'message': 'No se pudo actualizar el despacho'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/recordatorios_activos')
@login_required
def recordatorios_activos():
    """Ver recordatorios activos del usuario o área"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener área del usuario actual
    cursor.execute('SELECT area_id FROM usuarios WHERE id = %s', (session['user_id'],))
    user_area = cursor.fetchone()

    query = '''
        SELECT r.*, u.nombre as usuario_nombre, a.nombre as area_nombre
        FROM recordatorios r
        LEFT JOIN usuarios u ON r.usuario_id = u.id
        LEFT JOIN areas a ON r.area_id = a.id
        WHERE r.activo = TRUE AND r.fecha_recordatorio <= CURRENT_DATE
    '''
    params = []

    # Filtrar por usuario o área si no es admin
    if session['user_role'] != 'admin':
        query += ' AND (r.usuario_id = %s OR r.area_id = %s)'
        params.extend([session['user_id'], user_area['area_id'] if user_area else None])

    query += ' ORDER BY r.fecha_recordatorio ASC'

    cursor.execute(query, params)
    recordatorios_list = cursor.fetchall()
    conn.close()

    return render_template('recordatorios.html', recordatorios=recordatorios_list)


@app.route('/marcar_recordatorio_enviado/<int:recordatorio_id>', methods=['POST'])
@login_required
def marcar_recordatorio_enviado(recordatorio_id):
    """Marcar un recordatorio como enviado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE recordatorios
        SET enviado = TRUE, fecha_envio = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (recordatorio_id,))

    conn.commit()
    conn.close()

    flash('Recordatorio marcado como enviado', 'success')
    return redirect(url_for('recordatorios_activos'))


@app.route('/calendario')
@login_required
def calendario():
    """Vista de calendario interactivo"""
    return render_template('calendario.html')


@app.route('/api/calendar_events')
@login_required
def api_calendar_events():
    """API para obtener eventos del calendario con focus en órdenes de compra"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    events = []

    # Obtener órdenes de compra con fechas de entrega
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, p.fecha_entrega, p.estado, p.prioridad,
               c.nombre as cliente_nombre,
               CASE 
                   WHEN p.fecha_entrega IS NOT NULL THEN 
                       EXTRACT(EPOCH FROM (p.fecha_entrega::timestamp - CURRENT_DATE::timestamp)) / 86400 
                   ELSE NULL 
               END AS dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.fecha_entrega IS NOT NULL AND p.estado NOT IN ('entregado', 'cancelado')
    ''')

    for row in cursor.fetchall():
        # Colores según estado
        color = '#6c757d'  # gris por defecto
        if row['estado'] == 'en_desarrollo':
            color = '#6c757d'
        elif row['estado'] == 'aprobado_produccion':
            color = '#0d6efd'
        elif row['estado'] in ['seccionado', 'enchapado', 'mecanizado']:
            color = '#fd7e14'
        elif row['estado'] == 'produccion_completa':
            color = '#20c997'
        elif row['estado'] == 'embalando':
            color = '#198754'
        elif row['estado'] == 'listo_despacho':
            color = '#dc3545'

        # Marcar como urgente si faltan pocos días
        if row['dias_restantes'] is not None and row['dias_restantes'] <= 3:
            color = '#dc3545'  # rojo para urgente

        events.append({
            'id': f'orden_{row["id"]}',
            'title': f'OC: {row["codigo"]} - {row["nombre"]}',
            'start': row["fecha_entrega"].isoformat(), # Format date for FullCalendar
            'type': 'orden_compra',
            'backgroundColor': color,
            'borderColor': color,
            'proyecto': row["nombre"],
            'cliente': row["cliente_nombre"],
            'estado': row["estado"],
            'prioridad': row["prioridad"],
            'dias_restantes': row["dias_restantes"],
            'codigo': row["codigo"]
        })

    # Obtener despachos programados
    cursor.execute('''
        SELECT d.id, d.codigo_despacho, d.fecha_programada, d.estado,
               p.nombre as proyecto_nombre, p.codigo as proyecto_codigo,
               c.nombre as cliente_nombre
        FROM despachos d
        LEFT JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE d.fecha_programada IS NOT NULL
    ''')

    for row in cursor.fetchall():
        events.append({
            'id': f'despacho_{row["id"]}',
            'title': f'Despacho: {row["proyecto_codigo"] or row["codigo_despacho"]}',
            'start': row["fecha_programada"].isoformat(), # Format date for FullCalendar
            'type': 'despacho',
            'backgroundColor': '#e83e8c',
            'borderColor': '#e83e8c',
            'proyecto': row["proyecto_nombre"] or 'Proyecto Manual',
            'cliente': row["cliente_nombre"] or 'Cliente Manual',
            'estado': row["estado"],
            'codigo_despacho': row["codigo_despacho"]
        })

    # Obtener recordatorios de producción
    cursor.execute('''
        SELECT r.id, r.titulo, r.fecha_recordatorio, r.mensaje, r.enviado,
               u.nombre as usuario_nombre, a.nombre as area_nombre
        FROM recordatorios r
        LEFT JOIN usuarios u ON r.usuario_id = u.id
        LEFT JOIN areas a ON r.area_id = a.id
        WHERE r.activo = TRUE AND r.fecha_recordatorio IS NOT NULL
        AND r.tipo IN ('proyecto', 'despacho', 'general')
    ''')

    for row in cursor.fetchall():
        events.append({
            'id': f'recordatorio_{row["id"]}',
            'title': f'Recordatorio: {row["titulo"]}',
            'start': row["fecha_recordatorio"].isoformat(), # Format date for FullCalendar
            'type': 'recordatorio',
            'backgroundColor': '#ffc107',
            'borderColor': '#ffc107',
            'textColor': '#000',
            'usuario': row["usuario_nombre"],
            'area': row["area_nombre"],
            'mensaje': row["mensaje"],
            'enviado': row["enviado"]
        })

    conn.close()
    return jsonify(events)


@app.route('/api/iniciar_proceso_orden/<int:orden_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_iniciar_proceso_orden(orden_id):
    """Iniciar proceso de fabricación para una orden de compra"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que la orden existe y está pendiente
        cursor.execute('SELECT estado, codigo FROM proyectos WHERE id = %s', (orden_id,))
        orden = cursor.fetchone()

        if not orden:
            return jsonify({'success': False, 'message': 'Orden no encontrada'})

        if orden['estado'] not in ['diseño', 'en_desarrollo']:
            return jsonify({'success': False, 'message': 'La orden no está en estado pendiente'})

        # Cambiar estado de la orden a en proceso
        cursor.execute('UPDATE proyectos SET estado = %s WHERE id = %s', ('aprobado_produccion', orden_id))

        # Cambiar estado de todas las órdenes de fabricación a aprobado_produccion
        cursor.execute('''
            UPDATE ordenes_fabricacion
            SET estado = %s, fecha_inicio = CURRENT_TIMESTAMP
            WHERE proyecto_id = %s AND estado = 'pendiente_fabricacion'
        ''', ('aprobado_produccion', orden_id))

        conn.commit()
        return jsonify({'success': True, 'message': f'Proceso iniciado para orden {orden["codigo"]}'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/terminar_orden/<int:orden_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def api_terminar_orden(orden_id):
    """Marcar una orden de compra como terminada"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que todas las órdenes de fabricación están terminadas (si existen)
        cursor.execute('''
            SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ordenes_fabricacion')
        ''')
        if cursor.fetchone()[0]:
            cursor.execute('''
                SELECT COUNT(*) FROM ordenes_fabricacion
                WHERE proyecto_id = %s AND estado NOT IN ('listo_embalaje', 'despachado', 'entregado')
            ''', (orden_id,))
            pendientes = cursor.fetchone()['count']

            if pendientes > 0:
                return jsonify({'success': False, 'message': 'Hay órdenes de fabricación pendientes de terminar'})

            # Marcar todas las órdenes de fabricación como entregadas
            cursor.execute('''
                UPDATE ordenes_fabricacion
                SET estado = 'entregado', fecha_entrega_real = CURRENT_TIMESTAMP
                WHERE proyecto_id = %s
            ''', (orden_id,))

        # Marcar orden como terminada
        cursor.execute('''
            UPDATE proyectos
            SET estado = 'entregado', fecha_entrega_real = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (orden_id,))

        conn.commit()
        return jsonify({'success': True, 'message': 'Orden marcada como terminada'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/iniciar_orden_fabricacion/<int:orden_fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_iniciar_orden_fabricacion(orden_fabricacion_id):
    """Iniciar una orden de fabricación específica"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar estado actual de la orden de fabricación
        cursor.execute('SELECT estado, codigo_orden FROM ordenes_fabricacion WHERE id = %s', (orden_fabricacion_id,))
        orden = cursor.fetchone()

        if not orden:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        if orden['estado'] not in ['pendiente_fabricacion', 'aprobado_diseño']:
            return jsonify({'success': False, 'message': 'La orden no está pendiente de producción'})

        # Cambiar estado de la orden de fabricación a primera etapa
        cursor.execute('''
            UPDATE ordenes_fabricacion
            SET estado = 'seccionado', fecha_inicio = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (orden_fabricacion_id,))

        conn.commit()
        return jsonify({'success': True, 'message': f'Orden de fabricación {orden["codigo_orden"]} iniciada'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/iniciar_produccion/<int:fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_iniciar_produccion(fabricacion_id):
    """Iniciar producción de una orden de fabricación específica"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar estado actual de la orden de fabricación
        cursor.execute('SELECT estado, codigo_orden FROM ordenes_fabricacion WHERE id = %s', (fabricacion_id,))
        fab = cursor.fetchone()

        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        if fab['estado'] not in ['pendiente_fabricacion', 'aprobado_diseño']:
            return jsonify({'success': False, 'message': 'La orden no está pendiente de producción'})

        # Cambiar a primera etapa de fabricación
        cursor.execute('''
            UPDATE ordenes_fabricacion
            SET estado = 'seccionado', fecha_inicio = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (fabricacion_id,))

        conn.commit()
        return jsonify({'success': True, 'message': f'Producción iniciada para {fab["codigo_orden"]}'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/avanzar_etapa_fabricacion/<int:fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_avanzar_etapa_fabricacion(fabricacion_id):
    """Avanzar una orden de fabricación a la siguiente etapa"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener estado actual de la orden de fabricación
        cursor.execute('SELECT estado, codigo_orden FROM ordenes_fabricacion WHERE id = %s', (fabricacion_id,))
        fab = cursor.fetchone()

        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        estado_actual = fab['estado']
        codigo_orden = fab['codigo_orden']

        # Definir secuencia de estados para órdenes de fabricación
        estados_secuencia = ['seccionado', 'enchapando', 'mecanizado', 'listo_embalaje']

        try:
            indice_actual = estados_secuencia.index(estado_actual)
            if indice_actual < len(estados_secuencia) - 1:
                nuevo_estado = estados_secuencia[indice_actual + 1]

                # Si es la última etapa, marcar fecha de terminación
                if nuevo_estado == 'listo_embalaje':
                    cursor.execute('''
                        UPDATE ordenes_fabricacion
                        SET estado = %s, fecha_entrega_real = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (nuevo_estado, fabricacion_id))
                else:
                    cursor.execute('UPDATE ordenes_fabricacion SET estado = %s WHERE id = %s',
                                 (nuevo_estado, fabricacion_id))

                conn.commit()
                return jsonify({'success': True, 'message': f'{codigo_orden} avanzado a: {nuevo_estado.replace("_", " ").title()}'})
            else:
                return jsonify({'success': False, 'message': 'Ya está en la etapa final'})

        except ValueError:
            return jsonify({'success': False, 'message': 'Estado actual no válido'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/retroceder_etapa_fabricacion/<int:fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def api_retroceder_etapa_fabricacion(fabricacion_id):
    """Retroceder una orden de fabricación a la etapa anterior"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener estado actual de la orden de fabricación
        cursor.execute('SELECT estado, codigo_orden FROM ordenes_fabricacion WHERE id = %s', (fabricacion_id,))
        fab = cursor.fetchone()

        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        estado_actual = fab['estado']
        codigo_orden = fab['codigo_orden']

        # Definir secuencia de estados para órdenes de fabricación
        estados_secuencia = ['pendiente_fabricacion', 'seccionado', 'enchapando', 'mecanizado', 'listo_embalaje']

        try:
            indice_actual = estados_secuencia.index(estado_actual)
            if indice_actual > 0:
                nuevo_estado = estados_secuencia[indice_actual - 1]
                cursor.execute('''
                    UPDATE ordenes_fabricacion
                    SET estado = %s, fecha_entrega_real = NULL
                    WHERE id = %s
                ''', (nuevo_estado, fabricacion_id))

                conn.commit()
                return jsonify({'success': True, 'message': f'{codigo_orden} retrocedido a: {nuevo_estado.replace("_", " ").title()}'})
            else:
                return jsonify({'success': False, 'message': 'No se puede retroceder más'})

        except ValueError:
            return jsonify({'success': False, 'message': 'Estado actual no válido'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/update_event_date', methods=['POST'])
@login_required
def api_update_event_date():
    """API para actualizar la fecha de un evento"""
    try:
        data = request.get_json()
        event_id = data['id']
        event_type = data['type']
        new_start = data['start']

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Extraer el ID numérico del event_id
        numeric_id = int(event_id.split('_')[1])

        if event_type == 'despacho':
            # Verificar permisos para despachos
            if session['user_role'] not in ['admin', 'general', 'despacho']:
                return jsonify({'success': False, 'message': 'Sin permisos para modificar despachos'})

            cursor.execute('''
                UPDATE despachos SET fecha_programada = %s WHERE id = %s
            ''', (new_start, numeric_id))

        elif event_type == 'tarea':
            cursor.execute('''
                UPDATE tareas SET fecha_programada = %s WHERE id = %s
            ''', (new_start, numeric_id))

        elif event_type == 'recordatorio':
            # Verificar permisos para recordatorios
            if session['user_role'] not in ['admin', 'general']:
                return jsonify({'success': False, 'message': 'Sin permisos para modificar recordatorios'})

            cursor.execute('''
                UPDATE recordatorios SET fecha_recordatorio = %s WHERE id = %s
            ''', (new_start, numeric_id))

        else:
            return jsonify({'success': False, 'message': 'Tipo de evento no válido'})

        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Fecha actualizada exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'No se encontró el evento'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al actualizar: {str(e)}'})
    finally:
        if 'conn' in locals():
            conn.close()


@app.route('/ordenes_fabricacion')
@login_required
def ordenes_fabricacion():
    """Vista de órdenes de fabricación organizadas por estado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Órdenes de fabricación pendientes
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.fecha_entrega_estimada,
               of.cantidad_tableros, of.estado, of.observaciones,
               p.codigo as proyecto_codigo, p.nombre as proyecto_nombre,
               c.nombre as cliente_nombre, of.fecha_entrega_real
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado IN ('pendiente_fabricacion', 'aprobado_diseño')
        ORDER BY of.fecha_entrega_estimada ASC
    ''')
    fabricacion_pendientes = cursor.fetchall()

    # Órdenes de fabricación en proceso
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.fecha_entrega_estimada,
               of.cantidad_tableros, of.estado, of.observaciones,
               p.codigo as proyecto_codigo, p.nombre as proyecto_nombre,
               c.nombre as cliente_nombre, of.fecha_entrega_real
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado IN ('enviado_produccion', 'seccionado', 'enchapando', 'mecanizado', 'listo_embalaje')
        ORDER BY of.fecha_entrega_estimada ASC
    ''')
    fabricacion_proceso = cursor.fetchall()

    # Órdenes de fabricación terminadas
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.fecha_entrega_estimada,
               of.cantidad_tableros, of.estado, of.observaciones,
               p.codigo as proyecto_codigo, p.nombre as proyecto_nombre,
               c.nombre as cliente_nombre, of.fecha_entrega_real
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado IN ('embalando', 'listo_despacho', 'despachado')
        ORDER BY of.fecha_entrega_real DESC
        LIMIT 20
    ''')
    fabricacion_terminadas = cursor.fetchall()

    conn.close()

    return render_template('ordenes_fabricacion.html',
                           fabricacion_pendientes=fabricacion_pendientes,
                           fabricacion_proceso=fabricacion_proceso,
                           fabricacion_terminadas=fabricacion_terminadas)


@app.route('/crear_orden_fabricacion', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def crear_orden_fabricacion():
    """Crear nueva orden de fabricación"""
    try:
        proyecto_id = request.form['proyecto_id']
        tipo_orden = request.form['tipo_orden']
        fecha_entrega_estimada = request.form['fecha_entrega_estimada']
        cantidad_tableros = request.form['cantidad_tableros']
        observaciones = request.form.get('observaciones', '').strip() or None
        categorias_seleccionadas = request.form.getlist('categorias_seleccionadas')

        if not categorias_seleccionadas:
            flash('Debe seleccionar al menos una categoría para fabricar', 'error')
            return redirect(url_for('ordenes_fabricacion'))

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Verificar que el proyecto existe
        cursor.execute('SELECT codigo, nombre FROM proyectos WHERE id = %s', (proyecto_id,))
        proyecto = cursor.fetchone()
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('ordenes_fabricacion'))

        # Generar código único para la orden
        cursor.execute('SELECT COUNT(*) FROM ordenes_fabricacion WHERE EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)')
        orden_numero = cursor.fetchone()['count'] + 1
        codigo_orden = f"OF-{datetime.now().year}-{orden_numero:04d}"

        # Crear orden de fabricación
        cursor.execute('''
            INSERT INTO ordenes_fabricacion (
                codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada,
                cantidad_tableros, estado, observaciones
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada,
              cantidad_tableros, 'pendiente_fabricacion', observaciones))
        orden_fabricacion_id = cursor.fetchone()['id']

        # Procesar categorías seleccionadas
        for categoria_data in categorias_seleccionadas:
            categoria_id, subcategoria_id = categoria_data.split(',')
            subcategoria_id = subcategoria_id if subcategoria_id else None

            # Agregar categoría a la orden de fabricación
            cursor.execute('''
                INSERT INTO orden_fabricacion_categorias (
                    orden_fabricacion_id, categoria_id, subcategoria_id
                ) VALUES (%s, %s, %s)
            ''', (orden_fabricacion_id, categoria_id, subcategoria_id))

            # Las categorías ahora se manejan solo a través de orden_fabricacion_categorias
            # No se crean pedidos de seguimiento separados

        conn.commit()
        conn.close()

        flash(f'Orden de fabricación {codigo_orden} creada exitosamente', 'success')
        return redirect(url_for('ordenes_fabricacion'))

    except Exception as e:
        flash(f'Error al crear orden de fabricación: {str(e)}', 'error')
        return redirect(url_for('ordenes_fabricacion'))


@app.route('/api/proyectos_disponibles_fabricacion')
@login_required
def api_proyectos_disponibles_fabricacion():
    """API para obtener proyectos disponibles para órdenes de fabricación"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN proyecto_categorias pc ON p.id = pc.proyecto_id
        WHERE p.estado NOT IN ('entregado', 'cancelado')
        GROUP BY p.id, p.codigo, p.nombre, c.nombre
        ORDER BY p.nombre
    ''')

    proyectos = []
    for row in cursor.fetchall():
        proyectos.append({
            'id': row['id'],
            'codigo': row['codigo'] or f'PROJ-{row["id"]}',
            'nombre': row['nombre'],
            'cliente': row['cliente_nombre'] or 'Sin cliente'
        })

    conn.close()
    return jsonify(proyectos)


@app.route('/api/categorias_proyecto/<int:proyecto_id>')
@login_required
def api_categorias_proyecto(proyecto_id):
    """API para obtener categorías de un proyecto"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT pc.categoria_id, pc.subcategoria_id,
               cat.nombre as categoria_nombre, subcat.nombre as subcategoria_nombre
        FROM proyecto_categorias pc
        JOIN categorias_producto cat ON pc.categoria_id = cat.id
        LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
        WHERE pc.proyecto_id = %s
        ORDER BY cat.nombre, subcat.nombre
    ''', (proyecto_id,))

    categorias = []
    for row in cursor.fetchall():
        categorias.append({
            'categoria_id': row['categoria_id'],
            'subcategoria_id': row['subcategoria_id'],
            'categoria_nombre': row['categoria_nombre'],
            'subcategoria_nombre': row['subcategoria_nombre']
        })

    conn.close()
    return jsonify(categorias)


@app.route('/eliminar_orden_fabricacion/<int:orden_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def eliminar_orden_fabricacion(orden_id):
    """Eliminar orden de fabricación"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Verificar que la orden existe
        cursor.execute('SELECT codigo_orden, estado FROM ordenes_fabricacion WHERE id = %s', (orden_id,))
        orden = cursor.fetchone()

        if not orden:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        codigo_orden, estado = orden['codigo_orden'], orden['estado']

        # Solo permitir eliminar órdenes pendientes
        if estado not in ['pendiente_fabricacion', 'aprobado_diseño']:
            return jsonify({'success': False, 'message': 'No se puede eliminar una orden en proceso o terminada'})

        # Eliminar categorías de la orden
        cursor.execute('DELETE FROM orden_fabricacion_categorias WHERE orden_fabricacion_id = %s', (orden_id,))

        # Eliminar la orden
        cursor.execute('DELETE FROM ordenes_fabricacion WHERE id = %s', (orden_id,))

        conn.commit()
        return jsonify({'success': True, 'message': f'Orden {codigo_orden} eliminada exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al eliminar orden: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/clientes_activos')
@login_required
def api_clientes_activos():
    """API para obtener clientes activos"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes = []
    for row in cursor.fetchall():
        clientes.append({
            'id': row['id'],
            'nombre': row['nombre']
        })

    conn.close()
    return jsonify(clientes)


@app.route('/api/categorias')
@login_required
def api_categorias():
    """API para obtener categorías disponibles"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('SELECT id, nombre FROM categorias_producto WHERE activo = TRUE ORDER BY nombre ASC')
    categorias = []
    for row in cursor.fetchall():
        categorias.append({
            'id': row['id'],
            'nombre': row['nombre']
        })

    conn.close()
    return jsonify(categorias)


@app.route('/api/subcategorias/<int:categoria_id>')
@login_required
def api_subcategorias(categoria_id):
    """API para obtener subcategorías de una categoría"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, nombre FROM subcategorias_producto
        WHERE categoria_id = %s AND activo = TRUE
        ORDER BY nombre ASC
    ''', (categoria_id,))

    subcategorias = []
    for row in cursor.fetchall():
        subcategorias.append({
            'id': row['id'],
            'nombre': row['nombre']
        })

    conn.close()
    return jsonify(subcategorias)


@app.route('/api/proyectos_cliente/<int:cliente_id>')
@login_required
def api_proyectos_cliente(cliente_id):
    """API para obtener proyectos de un cliente específico"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, codigo, nombre
        FROM proyectos
        WHERE cliente_id = %s AND (archivado IS NULL OR archivado = FALSE)
        ORDER BY created_at DESC
    ''', (cliente_id,))

    proyectos = []
    for row in cursor.fetchall():
        proyectos.append({
            'id': row['id'],
            'codigo': row['codigo'] or f'PROJ-{row["id"]}',
            'nombre': row['nombre']
        })

    conn.close()
    return jsonify(proyectos)


@app.route('/crear_orden_fabricacion_desde_oc', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def crear_orden_fabricacion_desde_oc():
    """Crear orden de fabricación desde una orden de compra"""
    try:
        proyecto_id = request.form['proyecto_id']
        tipo_orden = request.form['tipo_orden']
        fecha_entrega_estimada = request.form['fecha_entrega_estimada']
        cantidad_tableros = request.form['cantidad_tableros']
        observaciones = request.form.get('observaciones', '').strip() or None
        categorias_seleccionadas = request.form.getlist('categorias_seleccionadas')

        if not categorias_seleccionadas:
            flash('Debe seleccionar al menos una categoría para fabricar', 'error')
            return redirect(url_for('ordenes_compra'))

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Verificar que el proyecto existe
        cursor.execute('SELECT codigo, nombre FROM proyectos WHERE id = %s', (proyecto_id,))
        proyecto = cursor.fetchone()
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('ordenes_compra'))

        # Generar código único para la orden
        cursor.execute('SELECT COUNT(*) FROM ordenes_fabricacion WHERE EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)')
        orden_numero = cursor.fetchone()['count'] + 1
        codigo_orden = f"OF-{datetime.now().year}-{orden_numero:04d}"

        # Crear orden de fabricación
        cursor.execute('''
            INSERT INTO ordenes_fabricacion (
                codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada,
                cantidad_tableros, estado, observaciones
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada,
              cantidad_tableros, 'pendiente_fabricacion', observaciones))
        orden_fabricacion_id = cursor.fetchone()['id']

        # Procesar categorías seleccionadas y crear pedidos de seguimiento
        for categoria_data in categorias_seleccionadas:
            categoria_id, subcategoria_id = categoria_data.split(',')
            subcategoria_id = subcategoria_id if subcategoria_id else None

            # Agregar categoría a la orden de fabricación
            cursor.execute('''
                INSERT INTO orden_fabricacion_categorias (
                    orden_fabricacion_id, categoria_id, subcategoria_id
                ) VALUES (%s, %s, %s)
            ''', (orden_fabricacion_id, categoria_id, subcategoria_id))

            # Las categorías ahora se manejan solo a través de orden_fabricacion_categorias
            # No se crean pedidos de seguimiento separados

        conn.commit()
        conn.close()

        flash(f'Orden de fabricación {codigo_orden} creada exitosamente', 'success')
        return redirect(url_for('ordenes_compra'))

    except Exception as e:
        flash(f'Error al crear orden de fabricación: {str(e)}', 'error')
        return redirect(url_for('ordenes_compra'))


@app.route('/api/proyectos_para_despacho')
@login_required
@role_required(['admin', 'general', 'despacho'])
def api_proyectos_para_despacho():
    """API para obtener proyectos listos para despacho"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('fabricacion', 'control_calidad', 'embalaje', 'despacho')
        ORDER BY p.nombre
    ''')

    proyectos = []
    for row in cursor.fetchall():
        proyectos.append({
            'id': row['id'],
            'codigo': row['codigo'] or f'PROJ-{row["id"]}',
            'nombre': row['nombre'],
            'cliente': row['cliente_nombre'] or 'Sin cliente'
        })

    conn.close()
    return jsonify(proyectos)


@app.route('/tareas_area')
@login_required
def tareas_area():
    """Vista principal de gestión de tareas por área"""
    user_role = session['user_role']

    # Redirigir según el rol del usuario
    if user_role == 'diseñador':
        return redirect(url_for('tareas_diseño'))
    elif user_role == 'operación':
        return redirect(url_for('tareas_operacion'))
    elif user_role == 'embalaje':
        return redirect(url_for('tareas_embalaje'))
    elif user_role == 'despacho':
        return redirect(url_for('tareas_despacho'))
    elif user_role in ['admin', 'general']:
        return redirect(url_for('tareas_general'))
    else:
        flash('No tienes acceso a gestión de tareas por área', 'error')
        return redirect(url_for('dashboard'))


@app.route('/tareas/diseño')
@login_required
@role_required(['diseñador', 'admin', 'general'])
def tareas_diseño():
    """Gestión de tareas de diseño"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.id, t.titulo, p.nombre as proyecto, p.codigo, t.estado,
               t.fecha_programada, t.descripcion, u.nombre as asignado,
               t.created_at
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.rol_asignado = 'diseñador' OR t.tipo = 'diseño'
        ORDER BY
            CASE t.estado
                WHEN 'pendiente' THEN 1
                WHEN 'en_progreso' THEN 2
                WHEN 'completada' THEN 3
            END,
            t.fecha_programada ASC
    ''')

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas_diseño.html', tareas=tareas_list)


@app.route('/tareas/operacion')
@login_required
@role_required(['operación', 'admin', 'general'])
def tareas_operacion():
    """Gestión de tareas de operación con etapas de fabricación"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Obtener tareas de operación/fabricación con sus etapas
    cursor.execute('''
        SELECT t.id, t.titulo, p.nombre as proyecto, p.codigo, t.estado,
               t.fecha_programada, t.descripcion, u.nombre as asignado,
               t.etapa_fabricacion, t.created_at
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.rol_asignado = 'operación' OR t.tipo = 'fabricación'
        ORDER BY
            CASE t.estado
                WHEN 'pendiente' THEN 1
                WHEN 'en_progreso' THEN 2
                WHEN 'completada' THEN 3
            END,
            CASE t.etapa_fabricacion
                WHEN 'seccionado' THEN 1
                WHEN 'enchapado' THEN 2
                WHEN 'mecanizado' THEN 3
                WHEN 'fabricacion_completo' THEN 4
                ELSE 5
            END,
            t.fecha_programada ASC
    ''')

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas_operacion.html', tareas=tareas_list)


@app.route('/tareas/embalaje')
@login_required
@role_required(['embalaje', 'admin', 'general'])
def tareas_embalaje():
    """Gestión de tareas de embalaje - solo fabricaciones completadas"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.id, t.titulo, p.nombre as proyecto, p.codigo, t.estado,
               t.fecha_programada, t.descripcion, u.nombre as asignado,
               t.created_at
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE (t.rol_asignado = 'embalaje' OR t.tipo = 'embalaje')
        AND EXISTS (
            SELECT 1 FROM tareas t2
            WHERE t2.proyecto_id = t.proyecto_id
            AND (t2.rol_asignado = 'operación' OR t2.tipo = 'fabricación')
            AND t2.estado = 'completada'
        )
        ORDER BY
            CASE t.estado
                WHEN 'pendiente' THEN 1
                WHEN 'en_progreso' THEN 2
                WHEN 'completada' THEN 3
            END,
            t.fecha_programada ASC
    ''')

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas_embalaje.html', tareas=tareas_list)


@app.route('/tareas/despacho')
@login_required
@role_required(['despacho', 'admin', 'general'])
def tareas_despacho():
    """Gestión de tareas de despacho"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.id, t.titulo, p.nombre as proyecto, p.codigo, t.estado,
               t.fecha_programada, t.descripcion, u.nombre as asignado,
               t.created_at, d.codigo_despacho, d.estado as despacho_estado
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        LEFT JOIN despachos d ON d.proyecto_id = t.proyecto_id
        WHERE t.rol_asignado = 'despacho' OR t.tipo = 'despacho'
        ORDER BY
            CASE t.estado
                WHEN 'pendiente' THEN 1
                WHEN 'en_progreso' THEN 2
                WHEN 'completada' THEN 3
            END,
            t.fecha_programada ASC
    ''')

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas_despacho.html', tareas=tareas_list)


@app.route('/tareas/general')
@login_required
@role_required(['admin', 'general'])
def tareas_general():
    """Vista general para admin/general - ve y modifica cualquier tarea"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.id, t.titulo, p.nombre as proyecto, p.codigo, t.estado,
               t.fecha_programada, t.descripcion, u.nombre as asignado,
               t.rol_asignado, t.tipo, t.etapa_fabricacion, t.created_at
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        ORDER BY
            t.rol_asignado,
            CASE t.estado
                WHEN 'pendiente' THEN 1
                WHEN 'en_progreso' THEN 2
                WHEN 'completada' THEN 3
            END,
            t.fecha_programada ASC
    ''')

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas_general.html', tareas=tareas_list)


@app.route('/avanzar_tarea/<int:tarea_id>', methods=['POST'])
@login_required
def avanzar_tarea(tarea_id):
    """Avanzar una tarea al siguiente estado"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener información actual de la tarea
        cursor.execute('''
            SELECT t.estado, t.rol_asignado, t.tipo,
                   t.proyecto_id, t.titulo, p.nombre as proyecto_nombre,
                   t.etapa_fabricacion
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            WHERE t.id = %s
        ''', (tarea_id,))

        tarea = cursor.fetchone()
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'})

        estado_actual, rol, tipo, proyecto_id, titulo, proyecto_nombre, etapa_actual = tarea['estado'], tarea['rol_asignado'], tarea['tipo'], tarea['proyecto_id'], tarea['titulo'], tarea['proyecto_nombre'], tarea['etapa_fabricacion']

        # Verificar permisos
        if session['user_role'] not in ['admin', 'general'] and session['user_role'] != rol:
            return jsonify({'success': False, 'message': 'Sin permisos para modificar esta tarea'})

        # Determinar siguiente estado según el rol
        if rol == 'diseñador':
            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                cursor.execute('UPDATE tareas SET estado = %s, fecha_inicio = %s WHERE id = %s',
                             (nuevo_estado, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                nuevo_estado = 'completada'
                cursor.execute('UPDATE tareas SET estado = %s, fecha_completada = %s WHERE id = %s',
                             (nuevo_estado, datetime.now(), tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        elif rol == 'operación':
            etapas = ['seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo']

            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                nueva_etapa = 'seccionado'
                cursor.execute('UPDATE tareas SET estado = %s, etapa_fabricacion = %s, fecha_inicio = %s WHERE id = %s',
                             (nuevo_estado, nueva_etapa, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                if etapa_actual in etapas:
                    indice_actual = etapas.index(etapa_actual)
                    if indice_actual < len(etapas) - 1:
                        nueva_etapa = etapas[indice_actual + 1]
                        cursor.execute('UPDATE tareas SET etapa_fabricacion = %s WHERE id = %s',
                                     (nueva_etapa, tarea_id))
                    else:
                        # Última etapa completada
                        cursor.execute('UPDATE tareas SET estado = %s, fecha_completada = %s WHERE id = %s',
                                     ('completada', datetime.now(), tarea_id))
                        nuevo_estado = 'completada'
                else:
                    nueva_etapa = 'seccionado'
                    cursor.execute('UPDATE tareas SET etapa_fabricacion = %s WHERE id = %s',
                                 (nueva_etapa, tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        else:  # embalaje, despacho, general
            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                cursor.execute('UPDATE tareas SET estado = %s, fecha_inicio = %s WHERE id = %s',
                             (nuevo_estado, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                nuevo_estado = 'completada'
                cursor.execute('UPDATE tareas SET estado = %s, fecha_completada = %s WHERE id = %s',
                             (nuevo_estado, datetime.now(), tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('tareas', %s, 'UPDATE', %s, %s)
        ''', (tarea_id, session['user_id'],
              json.dumps({'accion': 'avanzar_tarea', 'titulo': titulo, 'proyecto': proyecto_nombre})))

        conn.commit()
        return jsonify({'success': True, 'message': 'Tarea avanzada exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al avanzar tarea: {str(e)}'})
    finally:
        conn.close()


@app.route('/retroceder_tarea/<int:tarea_id>', methods=['POST'])
@login_required
def retroceder_tarea(tarea_id):
    """Retroceder una tarea al estado anterior"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Obtener información actual de la tarea
        cursor.execute('''
            SELECT t.estado, t.rol_asignado, t.tipo,
                   t.proyecto_id, t.titulo, p.nombre as proyecto_nombre,
                   t.etapa_fabricacion
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            WHERE t.id = %s
        ''', (tarea_id,))

        tarea = cursor.fetchone()
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'})

        estado_actual, rol, tipo, proyecto_id, titulo, proyecto_nombre, etapa_actual = tarea['estado'], tarea['rol_asignado'], tarea['tipo'], tarea['proyecto_id'], tarea['titulo'], tarea['proyecto_nombre'], tarea['etapa_fabricacion']

        # Solo admin y general pueden retroceder tareas
        if session['user_role'] not in ['admin', 'general']:
            return jsonify({'success': False, 'message': 'Sin permisos para retroceder tareas'})

        # Determinar estado anterior según el rol
        if rol == 'operación' and estado_actual == 'en_progreso' and etapa_actual:
            etapas = ['seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo']
            if etapa_actual in etapas:
                indice_actual = etapas.index(etapa_actual)
                if indice_actual > 0:
                    nueva_etapa = etapas[indice_actual - 1]
                    cursor.execute('UPDATE tareas SET etapa_fabricacion = %s WHERE id = %s',
                                 (nueva_etapa, tarea_id))
                else:
                    # Volver a pendiente
                    cursor.execute('UPDATE tareas SET estado = %s, etapa_fabricacion = NULL, fecha_inicio = NULL WHERE id = %s',
                                 ('pendiente', tarea_id))
        elif estado_actual == 'completada':
            cursor.execute('UPDATE tareas SET estado = %s, fecha_completada = NULL WHERE id = %s',
                         ('en_progreso', tarea_id))
        elif estado_actual == 'en_progreso':
            cursor.execute('UPDATE tareas SET estado = %s, fecha_inicio = NULL WHERE id = %s',
                         ('pendiente', tarea_id))
        else:
            return jsonify({'success': False, 'message': 'No se puede retroceder más'})

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('tareas', %s, 'UPDATE', %s, %s)
        ''', (tarea_id, session['user_id'],
              json.dumps({'accion': 'retroceder_tarea', 'titulo': titulo, 'proyecto': proyecto_nombre})))

        conn.commit()
        return jsonify({'success': True, 'message': 'Tarea retrocedida exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al retroceder tarea: {str(e)}'})
    finally:
        conn.close()


@app.route('/reportes')
@login_required
@role_required(['admin', 'general'])
def reportes():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Estadísticas por estado de proyecto
    cursor.execute('''
        SELECT estado, COUNT(*) as cantidad
        FROM proyectos
        GROUP BY estado
    ''')
    estados_proyecto = cursor.fetchall()

    # Tareas por rol
    cursor.execute('''
        SELECT rol_asignado, COUNT(*) as cantidad
        FROM tareas
        GROUP BY rol_asignado
    ''')
    tareas_rol = cursor.fetchall()

    # Productividad por usuario
    cursor.execute('''
        SELECT u.nombre, COUNT(t.id) as tareas_completadas
        FROM usuarios u
        LEFT JOIN tareas t ON u.id = t.usuario_asignado_id AND t.estado = 'completada'
        GROUP BY u.id, u.nombre
        ORDER BY tareas_completadas DESC
    ''')
    productividad = cursor.fetchall()

    conn.close()

    return render_template('reportes.html',
                           estados_proyecto=estados_proyecto,
                           tareas_rol=tareas_rol,
                           productividad=productividad)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)