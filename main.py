from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta
import json
from functools import wraps
import uuid

app = Flask(__name__)
app.secret_key = 'mobikit_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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

# Roles disponibles
ROLES = ['admin', 'general', 'diseñador', 'operación', 'embalaje', 'despacho']


def init_db():
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Ejecutar el schema completo desde el archivo SQL
    try:
        with open('database_schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            cursor.executescript(schema_sql)
    except FileNotFoundError:
        # Fallback: crear solo las tablas básicas si no existe el archivo de schema
        create_basic_tables(cursor)

    # Crear usuario admin por defecto si no existe
    cursor.execute('SELECT COUNT(*) FROM usuarios WHERE rol = "admin"')
    if cursor.fetchone()[0] == 0:
        admin_password = generate_password_hash('admin123')
        cursor.execute(
            '''
            INSERT INTO usuarios (username, password_hash, rol, nombre, email, activo)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('admin', admin_password, 'admin', 'Administrador',
              'admin@mobikit.com', True))

    conn.commit()
    conn.close()


def create_basic_tables(cursor):
    """Crear tablas básicas como fallback"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            descripcion TEXT,
            estado TEXT DEFAULT 'diseño',
            prioridad TEXT DEFAULT 'media',
            fecha_inicio DATE,
            fecha_entrega DATE,
            fecha_entrega_real DATE,
            diseñador_id INTEGER,
            supervisor_id INTEGER,
            presupuesto DECIMAL(12,2),
            costo_real DECIMAL(12,2),
            observaciones TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (diseñador_id) REFERENCES usuarios (id),
            FOREIGN KEY (supervisor_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tareas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
            FOREIGN KEY (usuario_asignado_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, password_hash, rol, nombre FROM usuarios WHERE username = ?',
            (username, ))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['user_role'] = user[2]
            session['user_name'] = user[3]
            flash(f'Bienvenido, {user[3]}!', 'success')
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Órdenes Pendientes (estado 'diseño' o 'en_desarrollo')
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad,
               julianday(p.fecha_entrega) - julianday('now') as dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('diseño', 'en_desarrollo')
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_pendientes = cursor.fetchall()

    # Órdenes en Proceso (tienen órdenes de fabricación activas)
    cursor.execute('''
        SELECT DISTINCT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad,
               julianday(p.fecha_entrega) - julianday('now') as dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN pedidos_seguimiento ps ON p.id = ps.proyecto_id
        WHERE ps.estado IN ('aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa')
        AND ps.estado != 'entregado'
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_proceso_raw = cursor.fetchall()

    # Para cada orden en proceso, obtener sus órdenes de fabricación
    ordenes_proceso = []
    for orden in ordenes_proceso_raw:
        cursor.execute('''
            SELECT ps.id, ps.codigo_pedido, ps.nombre, ps.estado, ps.fecha_entrega_estimada
            FROM pedidos_seguimiento ps
            WHERE ps.proyecto_id = ? AND ps.estado != 'entregado'
            ORDER BY ps.created_at ASC
        ''', (orden[0],))
        ordenes_fabricacion = cursor.fetchall()
        
        orden_dict = {
            'id': orden[0], 'codigo': orden[1], 'nombre': orden[2], 'cliente_nombre': orden[3],
            'fecha_entrega': orden[4], 'descripcion': orden[5], 'prioridad': orden[6],
            'dias_restantes': orden[7], 'ordenes_fabricacion': []
        }
        
        for fab in ordenes_fabricacion:
            fab_dict = {
                'id': fab[0], 'codigo_pedido': fab[1], 'nombre': fab[2], 
                'estado': fab[3], 'fecha_entrega_estimada': fab[4]
            }
            orden_dict['ordenes_fabricacion'].append(fab_dict)
        
        ordenes_proceso.append(orden_dict)

    # Órdenes Terminadas
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad, p.fecha_entrega_real
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('entregado', 'completado')
        ORDER BY p.fecha_entrega_real DESC
        LIMIT 10
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
    conn = sqlite3.connect('mobikit.db')
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
        cliente_info = {
            'id': cliente[0],
            'nombre': cliente[1],
            'rut': cliente[2],
            'email': cliente[3],
            'telefono': cliente[4],
            'direccion': cliente[5],
            'ciudad': cliente[6],
            'region': cliente[7],
            'contacto_principal': cliente[8],
            'observaciones': cliente[9],
            'total_proyectos': cliente[10],
            'proyectos': []
        }

        # Obtener proyectos del cliente
        cursor.execute('''
            SELECT p.id, p.codigo, p.nombre, p.descripcion, p.estado, p.prioridad,
                   p.fecha_entrega, p.presupuesto, u.nombre as diseñador_nombre,
                   julianday(p.fecha_entrega) - julianday('now') as dias_restantes
            FROM proyectos p
            LEFT JOIN usuarios u ON p.diseñador_id = u.id
            WHERE p.cliente_id = ?
            ORDER BY 
                CASE p.estado 
                    WHEN 'en_desarrollo' THEN 1
                    WHEN 'aprobado_produccion' THEN 2
                    WHEN 'seccionado' THEN 3
                    WHEN 'enchapado' THEN 4
                    WHEN 'mecanizado' THEN 5
                    WHEN 'produccion_completa' THEN 6
                    WHEN 'embalando' THEN 7
                    WHEN 'listo_despacho' THEN 8
                    WHEN 'entregado' THEN 9
                    ELSE 10
                END,
                p.fecha_entrega ASC
        ''', (cliente_info['id'],))

        proyectos = cursor.fetchall()
        for proyecto in proyectos:
            proyecto_dict = {
                'id': proyecto[0],
                'codigo': proyecto[1],
                'nombre': proyecto[2],
                'descripcion': proyecto[3],
                'estado': proyecto[4],
                'prioridad': proyecto[5],
                'fecha_entrega': proyecto[6],
                'presupuesto': proyecto[7],
                'diseñador_nombre': proyecto[8],
                'dias_restantes': int(proyecto[9]) if proyecto[9] is not None else None
            }
            cliente_info['proyectos'].append(proyecto_dict)

        clientes_con_proyectos.append(cliente_info)

    # Obtener clientes disponibles para nuevo proyecto
    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes_disponibles = cursor.fetchall()

    # Obtener diseñadores disponibles
    cursor.execute('SELECT id, nombre FROM usuarios WHERE rol = "diseñador" AND activo = TRUE ORDER BY nombre ASC')
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO clientes (
                nombre, rut, email, telefono, direccion, ciudad, region, 
                contacto_principal, observaciones, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nombre, rut, email, telefono, direccion, ciudad, region, 
              contacto_principal, observaciones, True))

        conn.commit()
        conn.close()

        flash('Cliente creado exitosamente', 'success')

    except sqlite3.IntegrityError as e:
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE clientes SET
                nombre = ?, rut = ?, email = ?, telefono = ?, direccion = ?,
                ciudad = ?, region = ?, contacto_principal = ?, observaciones = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (nombre, rut, email, telefono, direccion, ciudad, region, 
              contacto_principal, observaciones, cliente_id))

        conn.commit()
        conn.close()

        flash('Cliente actualizado exitosamente', 'success')

    except sqlite3.IntegrityError as e:
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
    try:
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar si tiene proyectos
        cursor.execute('SELECT COUNT(*) FROM proyectos WHERE cliente_id = ?', (cliente_id,))
        proyectos_count = cursor.fetchone()[0]

        if proyectos_count > 0:
            return jsonify({
                'success': False, 
                'message': f'No se puede eliminar el cliente porque tiene {proyectos_count} proyecto(s) asociado(s)'
            })

        # Eliminar cliente
        cursor.execute('DELETE FROM clientes WHERE id = ?', (cliente_id,))

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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Órdenes Pendientes
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad, p.presupuesto,
               julianday(p.fecha_entrega) - julianday('now') as dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('diseño', 'en_desarrollo')
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_pendientes_raw = cursor.fetchall()

    # Órdenes en Proceso
    cursor.execute('''
        SELECT DISTINCT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad, p.presupuesto,
               julianday(p.fecha_entrega) - julianday('now') as dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        INNER JOIN pedidos_seguimiento ps ON p.id = ps.proyecto_id
        WHERE ps.estado IN ('aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa')
        ORDER BY p.fecha_entrega ASC, p.prioridad DESC
    ''')
    ordenes_proceso_raw = cursor.fetchall()

    # Órdenes Terminadas
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre, p.fecha_entrega, 
               p.descripcion, p.prioridad, p.presupuesto, p.fecha_entrega_real
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('entregado', 'completado')
        ORDER BY p.fecha_entrega_real DESC
    ''')
    ordenes_terminadas_raw = cursor.fetchall()

    # Función para obtener categorías de una orden
    def obtener_categorias_orden(proyecto_id):
        cursor.execute('''
            SELECT cat.nombre, subcat.nombre
            FROM proyecto_categorias pc
            JOIN categorias_producto cat ON pc.categoria_id = cat.id
            LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
            WHERE pc.proyecto_id = ?
        ''', (proyecto_id,))
        categorias = []
        for cat_nombre, subcat_nombre in cursor.fetchall():
            categoria_texto = cat_nombre
            if subcat_nombre:
                categoria_texto += f" - {subcat_nombre}"
            categorias.append(categoria_texto)
        return categorias

    # Función para obtener órdenes de fabricación de una orden
    def obtener_ordenes_fabricacion(proyecto_id):
        cursor.execute('''
            SELECT ps.id, ps.codigo_pedido, ps.nombre, ps.estado, ps.fecha_entrega_estimada
            FROM pedidos_seguimiento ps
            WHERE ps.proyecto_id = ? AND ps.estado != 'entregado'
            ORDER BY ps.created_at ASC
        ''', (proyecto_id,))
        ordenes_fab = []
        for fab in cursor.fetchall():
            fab_dict = {
                'id': fab[0], 'codigo_pedido': fab[1], 'nombre': fab[2], 
                'estado': fab[3], 'fecha_entrega_estimada': fab[4]
            }
            ordenes_fab.append(fab_dict)
        return ordenes_fab

    # Procesar órdenes pendientes
    ordenes_pendientes = []
    for orden in ordenes_pendientes_raw:
        orden_dict = {
            'id': orden[0], 'codigo': orden[1], 'nombre': orden[2], 'cliente_nombre': orden[3],
            'fecha_entrega': orden[4], 'descripcion': orden[5], 'prioridad': orden[6], 
            'presupuesto': orden[7], 'dias_restantes': orden[8],
            'categorias': obtener_categorias_orden(orden[0])
        }
        ordenes_pendientes.append(orden_dict)

    # Procesar órdenes en proceso
    ordenes_proceso = []
    for orden in ordenes_proceso_raw:
        orden_dict = {
            'id': orden[0], 'codigo': orden[1], 'nombre': orden[2], 'cliente_nombre': orden[3],
            'fecha_entrega': orden[4], 'descripcion': orden[5], 'prioridad': orden[6], 
            'presupuesto': orden[7], 'dias_restantes': orden[8],
            'categorias': obtener_categorias_orden(orden[0]),
            'ordenes_fabricacion': obtener_ordenes_fabricacion(orden[0])
        }
        ordenes_proceso.append(orden_dict)

    # Procesar órdenes terminadas
    ordenes_terminadas = []
    for orden in ordenes_terminadas_raw:
        orden_dict = {
            'id': orden[0], 'codigo': orden[1], 'nombre': orden[2], 'cliente_nombre': orden[3],
            'fecha_entrega': orden[4], 'descripcion': orden[5], 'prioridad': orden[6], 
            'presupuesto': orden[7], 'fecha_entrega_real': orden[8]
        }
        ordenes_terminadas.append(orden_dict)

    conn.close()

    return render_template('ordenes_compra.html',
                           ordenes_pendientes=ordenes_pendientes,
                           ordenes_proceso=ordenes_proceso,
                           ordenes_terminadas=ordenes_terminadas)


@app.route('/ordenes_fabricacion')
@login_required
def ordenes_fabricacion():
    """Vista principal de órdenes de fabricación organizadas por estado"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Obtener órdenes de fabricación personalizadas pendientes
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada,
               of.cantidad_tableros, p.id as proyecto_id, p.codigo as proyecto_codigo, 
               c.nombre as cliente_nombre, p.prioridad, of.observaciones,
               julianday(of.fecha_entrega_estimada) - julianday('now') as dias_restantes
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado IN ('pendiente', 'aprobado_produccion')
        ORDER BY of.fecha_entrega_estimada ASC, p.prioridad DESC
    ''')
    ordenes_fabricacion_pendientes = cursor.fetchall()

    # Obtener órdenes de fabricación en proceso
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada,
               of.cantidad_tableros, p.id as proyecto_id, p.codigo as proyecto_codigo, 
               c.nombre as cliente_nombre, p.prioridad, of.observaciones
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado IN ('seccionado', 'enchapado', 'mecanizado')
        ORDER BY of.fecha_entrega_estimada ASC
    ''')
    ordenes_fabricacion_proceso = cursor.fetchall()

    # Obtener órdenes de fabricación terminadas
    cursor.execute('''
        SELECT of.id, of.codigo_orden, of.tipo_orden, of.estado, of.fecha_entrega_estimada,
               of.cantidad_tableros, p.id as proyecto_id, p.codigo as proyecto_codigo, 
               c.nombre as cliente_nombre, of.fecha_inicio, of.fecha_entrega_real
        FROM ordenes_fabricacion of
        JOIN proyectos p ON of.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE of.estado = 'produccion_completa'
        ORDER BY of.fecha_entrega_real DESC
    ''')
    ordenes_fabricacion_terminadas = cursor.fetchall()

    # También obtener pedidos de seguimiento legacy (para compatibilidad)
    cursor.execute('''
        SELECT ps.id, ps.codigo_pedido, ps.nombre, ps.estado, ps.fecha_entrega_estimada,
               p.id as proyecto_id, p.codigo as proyecto_codigo, c.nombre as cliente_nombre,
               cat.nombre as categoria_nombre, subcat.nombre as subcategoria_nombre,
               p.prioridad, ps.fecha_inicio,
               julianday(ps.fecha_entrega_estimada) - julianday('now') as dias_restantes
        FROM pedidos_seguimiento ps
        JOIN proyectos p ON ps.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        LEFT JOIN categorias_producto cat ON ps.categoria_id = cat.id
        LEFT JOIN subcategorias_producto subcat ON ps.subcategoria_id = subcat.id
        WHERE ps.orden_fabricacion_id IS NULL 
        AND ps.estado IN ('en_desarrollo', 'aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa')
        ORDER BY ps.fecha_entrega_estimada ASC, p.prioridad DESC
    ''')
    fabricacion_legacy = cursor.fetchall()

    conn.close()

    return render_template('ordenes_fabricacion.html',
                           ordenes_fabricacion_pendientes=ordenes_fabricacion_pendientes,
                           ordenes_fabricacion_proceso=ordenes_fabricacion_proceso,
                           ordenes_fabricacion_terminadas=ordenes_fabricacion_terminadas,
                           fabricacion_legacy=fabricacion_legacy)


@app.route('/orden_compra/<int:orden_id>')
@login_required
def orden_compra_detalle(orden_id):
    """Detalle de una orden de compra específica"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Obtener datos de la orden
    cursor.execute('''
        SELECT p.*, c.nombre as cliente_nombre, c.email as cliente_email,
               c.telefono as cliente_telefono, c.contacto_principal
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.id = ?
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
        WHERE pc.proyecto_id = ?
    ''', (orden_id,))
    categorias = cursor.fetchall()

    # Obtener órdenes de fabricación
    cursor.execute('''
        SELECT ps.*, cat.nombre as categoria_nombre, subcat.nombre as subcategoria_nombre
        FROM pedidos_seguimiento ps
        LEFT JOIN categorias_producto cat ON ps.categoria_id = cat.id
        LEFT JOIN subcategorias_producto subcat ON ps.subcategoria_id = subcat.id
        WHERE ps.proyecto_id = ?
        ORDER BY ps.created_at ASC
    ''', (orden_id,))
    ordenes_fabricacion = cursor.fetchall()

    conn.close()

    return render_template('orden_compra_detalle.html',
                           orden=orden,
                           categorias=categorias,
                           ordenes_fabricacion=ordenes_fabricacion)


@app.route('/proyectos')
@login_required
def proyectos():
    """Vista de proyectos organizados por cliente"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Obtener clientes con sus proyectos
    cursor.execute('''
        SELECT DISTINCT c.id, c.nombre, c.rut, c.email, c.telefono, c.contacto_principal
        FROM clientes c
        INNER JOIN proyectos p ON c.id = p.cliente_id
        WHERE c.activo = TRUE
        ORDER BY c.nombre ASC
    ''')
    clientes_con_proyectos = cursor.fetchall()

    proyectos_por_cliente = []

    for cliente in clientes_con_proyectos:
        cliente_info = {
            'id': cliente[0],
            'nombre': cliente[1],
            'rut': cliente[2],
            'email': cliente[3],
            'telefono': cliente[4],
            'contacto_principal': cliente[5],
            'proyectos': []
        }

        # Obtener proyectos del cliente
        cursor.execute('''
            SELECT p.id, p.codigo, p.nombre, p.descripcion, p.estado, p.prioridad,
                   p.fecha_entrega, p.presupuesto, u.nombre as diseñador_nombre,
                   julianday(p.fecha_entrega) - julianday('now') as dias_restantes
            FROM proyectos p
            LEFT JOIN usuarios u ON p.diseñador_id = u.id
            WHERE p.cliente_id = ?
            ORDER BY 
                CASE p.estado 
                    WHEN 'diseño' THEN 1
                    WHEN 'aprobado' THEN 2
                    WHEN 'producción' THEN 3
                    WHEN 'embalaje' THEN 4
                    WHEN 'despacho' THEN 5
                    WHEN 'entregado' THEN 6
                    WHEN 'cancelado' THEN 7
                    ELSE 8
                END,
                p.fecha_entrega ASC
        ''', (cliente_info['id'],))

        proyectos_raw = cursor.fetchall()

        # Obtener categorías para cada proyecto
        proyectos = []
        for proyecto in proyectos_raw:
            proyecto_dict = {
                'id': proyecto[0],
                'codigo': proyecto[1],
                'nombre': proyecto[2],
                'descripcion': proyecto[3],
                'estado': proyecto[4],
                'prioridad': proyecto[5],
                'fecha_entrega': proyecto[6],
                'presupuesto': proyecto[7],
                'diseñador_nombre': proyecto[8],
                'dias_restantes': int(proyecto[9]) if proyecto[9] is not None else None,
                'categorias': []
            }

            # Obtener categorías asociadas al proyecto
            cursor.execute('''
                SELECT cat.nombre, subcat.nombre
                FROM proyecto_categorias pc
                JOIN categorias_producto cat ON pc.categoria_id = cat.id
                LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
                WHERE pc.proyecto_id = ?
            ''', (proyecto[0],))

            categorias = cursor.fetchall()
            for cat_nombre, subcat_nombre in categorias:
                categoria_texto = cat_nombre
                if subcat_nombre:
                    categoria_texto += f" - {subcat_nombre}"
                proyecto_dict['categorias'].append(categoria_texto)

            cliente_info['proyectos'].append(proyecto_dict)

        proyectos_por_cliente.append(cliente_info)

    # Obtener clientes disponibles para nuevo proyecto
    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes_disponibles = cursor.fetchall()

    # Obtener diseñadores disponibles
    cursor.execute('SELECT id, nombre FROM usuarios WHERE rol = "diseñador" AND activo = TRUE ORDER BY nombre ASC')
    diseñadores_disponibles = cursor.fetchall()

    conn.close()

    fecha_hoy = datetime.now().date().strftime('%Y-%m-%d')

    return render_template('proyectos.html', 
                           proyectos_por_cliente=proyectos_por_cliente,
                           clientes_disponibles=clientes_disponibles,
                           diseñadores_disponibles=diseñadores_disponibles,
                           fecha_hoy=fecha_hoy)


@app.route('/proyecto/<int:proyecto_id>')
@login_required
def proyecto_detalle(proyecto_id):
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Datos del proyecto
    cursor.execute(
        '''
        SELECT p.*, u.nombre as diseñador
        FROM proyectos p
        LEFT JOIN usuarios u ON p.diseñador_id = u.id
        WHERE p.id = ?
    ''', (proyecto_id, ))
    proyecto = cursor.fetchone()

    # Tareas del proyecto
    cursor.execute(
        '''
        SELECT t.*, u.nombre as asignado
        FROM tareas t
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.proyecto_id = ?
        ORDER BY t.fecha_programada ASC
    ''', (proyecto_id, ))
    tareas = cursor.fetchall()

    conn.close()

    if not proyecto:
        flash('Proyecto no encontrado', 'error')
        return redirect(url_for('proyectos'))

    return render_template('proyecto_detalle.html',
                           proyecto=proyecto,
                           tareas=tareas)


@app.route('/nuevo_proyecto', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nuevo_proyecto():
    """Crear nuevo proyecto desde modal"""
    try:
        nombre = request.form['nombre']
        cliente_id = request.form['cliente_id']
        descripcion = request.form.get('descripcion', '').strip() or None
        prioridad = request.form.get('prioridad', 'media')
        fecha_inicio = request.form.get('fecha_inicio') or datetime.now().date()
        fecha_entrega = request.form.get('fecha_entrega') or None
        diseñador_id = request.form.get('diseñador_id') or None
        presupuesto = request.form.get('presupuesto')
        observaciones = request.form.get('observaciones', '').strip() or None

        # Convertir presupuesto a float si se proporciona
        if presupuesto:
            try:
                presupuesto = float(presupuesto)
            except ValueError:
                presupuesto = None

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar que el cliente existe
        cursor.execute('SELECT id FROM clientes WHERE id = ? AND activo = TRUE', (cliente_id,))
        if not cursor.fetchone():
            flash('Cliente no válido', 'error')
            return redirect(url_for('clientes'))

        # Generar código único del proyecto
        cursor.execute('SELECT COUNT(*) FROM proyectos WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
        proyecto_numero = cursor.fetchone()[0] + 1
        codigo_proyecto = f"MOB-{datetime.now().year}-{proyecto_numero:03d}"

        # Crear proyecto
        cursor.execute('''
            INSERT INTO proyectos (
                codigo, nombre, cliente_id, descripcion, estado, prioridad,
                fecha_inicio, fecha_entrega, diseñador_id, presupuesto, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (codigo_proyecto, nombre, cliente_id, descripcion, 'en_desarrollo', prioridad,
              fecha_inicio, fecha_entrega, diseñador_id, presupuesto, observaciones))

        proyecto_id = cursor.lastrowid

        # Crear tareas automáticas del ciclo de vida
        tareas_ciclo = [
            ('Diseño inicial', 'Crear diseño y planos del mueble', 'diseñador', 'diseño', 1),
            ('Revisión de diseño', 'Revisar y aprobar diseño', 'general', 'diseño', 3),
            ('Planificación de producción', 'Planificar proceso de fabricación', 'operación', 'fabricación', 5),
            ('Fabricación', 'Fabricar el mueble según especificaciones', 'operación', 'fabricación', 15),
            ('Control de calidad', 'Revisar calidad del producto terminado', 'operación', 'control_calidad', 18),
            ('Embalaje', 'Embalar producto para despacho', 'embalaje', 'embalaje', 20),
            ('Preparación de despacho', 'Preparar documentos y coordinar entrega', 'despacho', 'despacho', 22),
            ('Entrega', 'Entregar producto al cliente', 'despacho', 'despacho', 24)
        ]

        fecha_base = datetime.strptime(str(fecha_inicio), '%Y-%m-%d').date() if isinstance(fecha_inicio, str) else fecha_inicio

        for titulo, descripcion_tarea, rol, tipo, dias in tareas_ciclo:
            fecha_programada = fecha_base + timedelta(days=dias)
            cursor.execute('''
                INSERT INTO tareas (
                    proyecto_id, titulo, descripcion, rol_asignado, tipo, 
                    fecha_programada, estado, prioridad
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (proyecto_id, titulo, descripcion_tarea, rol, tipo, 
                  fecha_programada, 'pendiente', prioridad))

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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Actualizar proyecto
        cursor.execute('''
            UPDATE proyectos SET
                nombre = ?, descripcion = ?, prioridad = ?,
                fecha_entrega = ?, presupuesto = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (nombre, descripcion, prioridad, fecha_entrega, presupuesto, proyecto_id))

        conn.commit()
        conn.close()

        flash('Proyecto actualizado exitosamente', 'success')

    except Exception as e:
        flash(f'Error al actualizar proyecto: {str(e)}', 'error')

    return redirect(url_for('clientes'))


@app.route('/tareas')
@login_required
def tareas():
    """Redirigir al nuevo sistema de gestión de pedidos por estado"""
    return redirect(url_for('gestion_pedidos'))


@app.route('/tarea/<int:tarea_id>')
@login_required
def tarea_detalle(tarea_id):
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute(
        '''
        SELECT t.*, p.nombre as proyecto, u.nombre as asignado
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.id = ?
    ''', (tarea_id, ))
    tarea = cursor.fetchone()

    cursor.execute(
        '''
        SELECT * FROM evidencias WHERE tarea_id = ? ORDER BY uploaded_at DESC
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Verificar que el usuario puede completar esta tarea
    cursor.execute(
        '''
        SELECT rol_asignado, usuario_asignado_id FROM tareas WHERE id = ?
    ''', (tarea_id, ))
    tarea = cursor.fetchone()

    if not tarea:
        flash('Tarea no encontrada', 'error')
        return redirect(url_for('tareas'))

    if (tarea[0] != session['user_role'] and tarea[1] != session['user_id']
            and session['user_role'] != 'admin'):
        flash('No tienes permisos para completar esta tarea', 'error')
        return redirect(url_for('tarea_detalle', tarea_id=tarea_id))

    cursor.execute(
        '''
        UPDATE tareas SET estado = 'completada', fecha_completada = ?
        WHERE id = ?
    ''', (datetime.now(), tarea_id))

    conn.commit()
    conn.close()

    flash('Tarea completada exitosamente', 'success')
    return redirect(url_for('tarea_detalle', tarea_id=tarea_id))


@app.route('/usuarios')
@login_required
@role_required(['admin'])
def usuarios():
    conn = sqlite3.connect('mobikit.db')
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

    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''
            INSERT INTO usuarios (username, password_hash, nombre, rol, email)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password_hash, nombre, rol, email))
        conn.commit()
        flash('Usuario creado exitosamente', 'success')
    except sqlite3.IntegrityError:
        flash('El nombre de usuario ya existe', 'error')
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Generar código único para el despacho
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
        despacho_numero = cursor.fetchone()[0] + 1
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
            info_completa += f"\nHORA PROGRAMADA: {hora_programada}"
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (codigo_despacho, transportista, conductor, 
              telefono_conductor, vehiculo_patente, direccion_entrega, 
              fecha_despacho, info_completa, 'programado'))

        despacho_id = cursor.lastrowid

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
                            VALUES (?, ?, ?, ?, ?)
                        ''', (despacho_id, tipo_archivo, file.filename, file_path, len(file.read()) if hasattr(file, 'read') else 0))

        # Crear recordatorios automáticos
        fecha_despacho_dt = datetime.strptime(fecha_despacho, '%Y-%m-%d').date()

        # Recordatorio 5 días antes
        fecha_recordatorio = fecha_despacho_dt - timedelta(days=5)
        cursor.execute('SELECT id FROM areas WHERE nombre = "Despacho" LIMIT 1')
        area_despacho = cursor.fetchone()
        area_id = area_despacho[0] if area_despacho else None

        titulo_recordatorio = f"Preparar despacho {codigo_despacho}"
        mensaje_recordatorio = f"Despacho programado para {fecha_despacho}.\nCliente: {cliente_nombre}\nObra: {obra_nombre}"
        if direccion_entrega:
            mensaje_recordatorio += f"\nDirección: {direccion_entrega}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje, 
                fecha_recordatorio, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar que el cliente existe
        cursor.execute('SELECT nombre FROM clientes WHERE id = ? AND activo = TRUE', (cliente_id,))
        cliente = cursor.fetchone()
        if not cliente:
            flash('Cliente no válido', 'error')
            return redirect(request.referrer or url_for('despachos'))

        cliente_nombre = cliente[0]

        # Si no se seleccionó proyecto existente, crear uno nuevo
        if not proyecto_id:
            if not proyecto_nombre:
                flash('Debe especificar un nombre para el nuevo proyecto', 'error')
                return redirect(request.referrer or url_for('despachos'))

            # Generar código único del proyecto
            cursor.execute('SELECT COUNT(*) FROM proyectos WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
            proyecto_numero = cursor.fetchone()[0] + 1
            codigo_proyecto = f"MOB-{datetime.now().year}-{proyecto_numero:03d}"

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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (codigo_proyecto, proyecto_nombre, cliente_id, descripcion, 'pendiente_fabricacion', prioridad,
                  datetime.now().date(), fecha_despacho, presupuesto_num))

            proyecto_id = cursor.lastrowid

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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (proyecto_id, titulo, descripcion_tarea, rol, tipo, 
                      fecha_programada, 'pendiente', prioridad, etapa_fab))

        else:
            # Verificar que el proyecto existe y pertenece al cliente
            cursor.execute('''
                SELECT p.nombre, p.codigo FROM proyectos p 
                WHERE p.id = ? AND p.cliente_id = ?
            ''', (proyecto_id, cliente_id))
            proyecto_info = cursor.fetchone()
            if not proyecto_info:
                flash('Proyecto no válido para el cliente seleccionado', 'error')
                return redirect(request.referrer or url_for('despachos'))

            proyecto_nombre = proyecto_info[0]
            codigo_proyecto = proyecto_info[1]

            # Actualizar estado del proyecto a pendiente_fabricacion si no lo está
            cursor.execute('''
                UPDATE proyectos SET estado = 'pendiente_fabricacion', 
                fecha_entrega = ?, prioridad = ?
                WHERE id = ?
            ''', (fecha_despacho, prioridad, proyecto_id))

        # Crear el despacho
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
        despacho_numero = cursor.fetchone()[0] + 1
        codigo_despacho = f"DESP-{datetime.now().year}-{despacho_numero:04d}"

        observaciones_completas = f"ORDEN DE PRODUCCIÓN AUTOMÁTICA\nCliente: {cliente_nombre}\nProyecto: {proyecto_nombre}"
        if observaciones:
            observaciones_completas += f"\n\nObservaciones: {observaciones}"

        cursor.execute('''
            INSERT INTO despachos (
                proyecto_id, codigo_despacho, transportista, direccion_entrega, 
                fecha_programada, observaciones, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (proyecto_id, codigo_despacho, transportista, direccion_entrega, 
              fecha_despacho, observaciones_completas, 'programado'))

        despacho_id = cursor.lastrowid

        # Crear recordatorios
        fecha_despacho_dt = datetime.strptime(fecha_despacho, '%Y-%m-%d').date()

        # Recordatorio para iniciar producción (inmediato)
        cursor.execute('SELECT id FROM areas WHERE nombre = "Producción" LIMIT 1')
        area_produccion = cursor.fetchone()
        area_prod_id = area_produccion[0] if area_produccion else None

        titulo_produccion = f"Nueva orden de producción: {codigo_proyecto}"
        mensaje_produccion = f"Se ha creado una nueva orden de producción para el proyecto {proyecto_nombre}.\nCliente: {cliente_nombre}\nFecha límite de despacho: {fecha_despacho}\nPrioridad: {prioridad.upper()}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje, 
                fecha_recordatorio, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('proyecto', proyecto_id, area_prod_id, titulo_produccion, 
              mensaje_produccion, datetime.now().date(), True))

        # Recordatorio de despacho 5 días antes
        fecha_recordatorio_despacho = fecha_despacho_dt - timedelta(days=5)
        cursor.execute('SELECT id FROM areas WHERE nombre = "Despacho" LIMIT 1')
        area_despacho = cursor.fetchone()
        area_desp_id = area_despacho[0] if area_despacho else None

        titulo_despacho = f"Preparar despacho {codigo_despacho}"
        mensaje_despacho = f"Despacho programado para {fecha_despacho}.\nProyecto: {proyecto_nombre}\nCliente: {cliente_nombre}\nDirección: {direccion_entrega}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje, 
                fecha_recordatorio, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.*, 
               CASE 
                   WHEN p.nombre IS NOT NULL THEN p.nombre
                   ELSE 'Proyecto Manual'
               END as proyecto_nombre, 
               CASE 
                   WHEN p.codigo IS NOT NULL THEN p.codigo
                   ELSE d.codigo_despacho
               END as proyecto_codigo,
               CASE 
                   WHEN c.nombre IS NOT NULL THEN c.nombre
                   ELSE 'Cliente Manual'
               END as cliente_nombre
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Obtener datos del despacho
    cursor.execute('''
        SELECT d.*, p.nombre as proyecto_nombre, p.codigo as proyecto_codigo,
               c.nombre as cliente_nombre, c.direccion as cliente_direccion
        FROM despachos d
        JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE d.id = ?
    ''', (despacho_id,))

    despacho = cursor.fetchone()

    if not despacho:
        flash('Despacho no encontrado', 'error')
        return redirect(url_for('despachos'))

    # Obtener archivos del despacho
    cursor.execute('''
        SELECT * FROM despacho_archivos
        WHERE despacho_id = ?
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
    conn = sqlite3.connect('mobikit.db')
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
                    transportista = ?, conductor = ?, telefono_conductor = ?,
                    vehiculo_patente = ?, direccion_entrega = ?, observaciones = ?,
                    fecha_programada = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
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
                            VALUES (?, ?, ?, ?)
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
        JOIN proyectos p ON d.proyecto_id = p.id
        WHERE d.id = ?
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener archivos para eliminarlos del sistema
        cursor.execute('SELECT ruta_archivo FROM despacho_archivos WHERE despacho_id = ?', (despacho_id,))
        archivos = cursor.fetchall()

        # Eliminar archivos del sistema de archivos
        for archivo in archivos:
            delete_file(archivo[0])

        # Eliminar registros de archivos
        cursor.execute('DELETE FROM despacho_archivos WHERE despacho_id = ?', (despacho_id,))

        # Eliminar recordatorios asociados
        cursor.execute('DELETE FROM recordatorios WHERE tipo = "despacho" AND referencia_id = ?', (despacho_id,))

        # Eliminar despacho
        cursor.execute('DELETE FROM despachos WHERE id = ?', (despacho_id,))

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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener información del archivo
        cursor.execute('SELECT despacho_id, ruta_archivo FROM despacho_archivos WHERE id = ?', (archivo_id,))
        archivo = cursor.fetchone()

        if archivo:
            despacho_id, ruta_archivo = archivo

            # Eliminar archivo del sistema
            delete_file(ruta_archivo)

            # Eliminar registro de la base de datos
            cursor.execute('DELETE FROM despacho_archivos WHERE id = ?', (archivo_id,))
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE despachos SET estado = 'en_transito', fecha_despacho = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'programado'
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE despachos SET estado = 'entregado', fecha_entrega = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'en_transito'
        ''', (despacho_id,))

        # También actualizar el proyecto como entregado
        cursor.execute('''
            UPDATE proyectos SET estado = 'entregado', fecha_entrega_real = CURRENT_TIMESTAMP
            WHERE id = (SELECT proyecto_id FROM despachos WHERE id = ?)
        ''', (despacho_id,))

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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Obtener área del usuario actual
    cursor.execute('SELECT area_id FROM usuarios WHERE id = ?', (session['user_id'],))
    user_area = cursor.fetchone()

    query = '''
        SELECT r.*, u.nombre as usuario_nombre, a.nombre as area_nombre
        FROM recordatorios r
        LEFT JOIN usuarios u ON r.usuario_id = u.id
        LEFT JOIN areas a ON r.area_id = a.id
        WHERE r.activo = TRUE AND r.fecha_recordatorio <= date('now', '+7 days')
    '''
    params = []

    # Filtrar por usuario o área si no es admin
    if session['user_role'] != 'admin':
        query += ' AND (r.usuario_id = ? OR r.area_id = ?)'
        params.extend([session['user_id'], user_area[0] if user_area else None])

    query += ' ORDER BY r.fecha_recordatorio ASC'

    cursor.execute(query, params)
    recordatorios_list = cursor.fetchall()
    conn.close()

    return render_template('recordatorios.html', recordatorios=recordatorios_list)


@app.route('/marcar_recordatorio_enviado/<int:recordatorio_id>', methods=['POST'])
@login_required
def marcar_recordatorio_enviado(recordatorio_id):
    """Marcar un recordatorio como enviado"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE recordatorios 
        SET enviado = TRUE, fecha_envio = CURRENT_TIMESTAMP 
        WHERE id = ?
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    events = []

    # Obtener órdenes de compra con fechas de entrega
    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, p.fecha_entrega, p.estado, p.prioridad,
               c.nombre as cliente_nombre,
               julianday(p.fecha_entrega) - julianday('now') as dias_restantes
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.fecha_entrega IS NOT NULL AND p.estado NOT IN ('entregado', 'cancelado')
    ''')

    for row in cursor.fetchall():
        # Colores según estado
        color = '#6c757d'  # gris por defecto
        if row[4] == 'en_desarrollo':
            color = '#6c757d'
        elif row[4] == 'aprobado_produccion':
            color = '#0d6efd'
        elif row[4] in ['seccionado', 'enchapado', 'mecanizado']:
            color = '#fd7e14'
        elif row[4] == 'produccion_completa':
            color = '#20c997'
        elif row[4] == 'embalando':
            color = '#198754'
        elif row[4] == 'listo_despacho':
            color = '#dc3545'

        # Marcar como urgente si faltan pocos días
        if row[7] is not None and row[7] <= 3:
            color = '#dc3545'  # rojo para urgente

        events.append({
            'id': f'orden_{row[0]}',
            'title': f'OC: {row[1]} - {row[2]}',
            'start': row[3],
            'type': 'orden_compra',
            'backgroundColor': color,
            'borderColor': color,
            'proyecto': row[2],
            'cliente': row[6],
            'estado': row[4],
            'prioridad': row[5],
            'dias_restantes': row[7],
            'codigo': row[1]
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
            'id': f'despacho_{row[0]}',
            'title': f'Despacho: {row[5] or row[1]}',
            'start': row[2],
            'type': 'despacho',
            'backgroundColor': '#e83e8c',
            'borderColor': '#e83e8c',
            'proyecto': row[4] or 'Proyecto Manual',
            'cliente': row[6] or 'Cliente Manual',
            'estado': row[3],
            'codigo_despacho': row[1]
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
            'id': f'recordatorio_{row[0]}',
            'title': f'Recordatorio: {row[1]}',
            'start': row[2],
            'type': 'recordatorio',
            'backgroundColor': '#ffc107',
            'borderColor': '#ffc107',
            'textColor': '#000',
            'usuario': row[5],
            'area': row[6],
            'mensaje': row[3],
            'enviado': row[4]
        })

    conn.close()
    return jsonify(events)


@app.route('/api/iniciar_proceso_orden/<int:orden_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_iniciar_proceso_orden(orden_id):
    """Iniciar proceso de fabricación para una orden de compra"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Verificar que la orden existe y está pendiente
        cursor.execute('SELECT estado, codigo FROM proyectos WHERE id = ?', (orden_id,))
        orden = cursor.fetchone()
        
        if not orden:
            return jsonify({'success': False, 'message': 'Orden no encontrada'})

        if orden[0] not in ['diseño', 'en_desarrollo']:
            return jsonify({'success': False, 'message': 'La orden no está en estado pendiente'})

        # Cambiar estado de la orden a en proceso
        cursor.execute('UPDATE proyectos SET estado = ? WHERE id = ?', ('aprobado_produccion', orden_id))

        # Cambiar estado de todas las órdenes de fabricación a aprobado_produccion
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = ?, fecha_inicio = CURRENT_TIMESTAMP 
            WHERE proyecto_id = ? AND estado = 'en_desarrollo'
        ''', ('aprobado_produccion', orden_id))

        conn.commit()
        return jsonify({'success': True, 'message': f'Proceso iniciado para orden {orden[1]}'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/terminar_orden/<int:orden_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def api_terminar_orden(orden_id):
    """Marcar una orden de compra como terminada"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Verificar que todas las órdenes de fabricación están terminadas
        cursor.execute('''
            SELECT COUNT(*) FROM pedidos_seguimiento 
            WHERE proyecto_id = ? AND estado != 'produccion_completa'
        ''', (orden_id,))
        pendientes = cursor.fetchone()[0]

        if pendientes > 0:
            return jsonify({'success': False, 'message': 'Hay órdenes de fabricación pendientes de terminar'})

        # Marcar orden como terminada
        cursor.execute('''
            UPDATE proyectos 
            SET estado = 'entregado', fecha_entrega_real = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (orden_id,))

        # Marcar todas las órdenes de fabricación como entregadas
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = 'entregado', fecha_entrega_real = CURRENT_TIMESTAMP 
            WHERE proyecto_id = ?
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
    """Iniciar una orden de fabricación personalizada"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Verificar estado actual de la orden de fabricación
        cursor.execute('SELECT estado, codigo_orden FROM ordenes_fabricacion WHERE id = ?', (orden_fabricacion_id,))
        orden = cursor.fetchone()
        
        if not orden:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        if orden[0] not in ['pendiente', 'aprobado_produccion']:
            return jsonify({'success': False, 'message': 'La orden no está pendiente de producción'})

        # Cambiar estado de la orden de fabricación a primera etapa
        cursor.execute('''
            UPDATE ordenes_fabricacion 
            SET estado = 'seccionado', fecha_inicio = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (orden_fabricacion_id,))

        # También actualizar todos los pedidos de seguimiento asociados
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = 'seccionado', fecha_inicio = CURRENT_TIMESTAMP 
            WHERE orden_fabricacion_id = ?
        ''', (orden_fabricacion_id,))

        conn.commit()
        return jsonify({'success': True, 'message': f'Orden de fabricación {orden[1]} iniciada'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/iniciar_produccion/<int:fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_iniciar_produccion(fabricacion_id):
    """Iniciar producción de una orden de fabricación específica"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Verificar estado actual
        cursor.execute('SELECT estado, codigo_pedido FROM pedidos_seguimiento WHERE id = ?', (fabricacion_id,))
        fab = cursor.fetchone()
        
        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        if fab[0] not in ['en_desarrollo', 'aprobado_produccion']:
            return jsonify({'success': False, 'message': 'La orden no está pendiente de producción'})

        # Cambiar a primera etapa de fabricación
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = 'seccionado', fecha_inicio = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (fabricacion_id,))

        conn.commit()
        return jsonify({'success': True, 'message': f'Producción iniciada para {fab[1]}'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()


@app.route('/api/avanzar_etapa_fabricacion/<int:fabricacion_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def api_avanzar_etapa_fabricacion(fabricacion_id):
    """Avanzar una orden de fabricación a la siguiente etapa"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener estado actual
        cursor.execute('SELECT estado, codigo_pedido FROM pedidos_seguimiento WHERE id = ?', (fabricacion_id,))
        fab = cursor.fetchone()
        
        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        estado_actual = fab[0]
        codigo_pedido = fab[1]

        # Definir secuencia de estados
        estados_secuencia = ['seccionado', 'enchapado', 'mecanizado', 'produccion_completa']

        try:
            indice_actual = estados_secuencia.index(estado_actual)
            if indice_actual < len(estados_secuencia) - 1:
                nuevo_estado = estados_secuencia[indice_actual + 1]
                
                # Si es la última etapa, marcar fecha de terminación
                if nuevo_estado == 'produccion_completa':
                    cursor.execute('''
                        UPDATE pedidos_seguimiento 
                        SET estado = ?, fecha_entrega_real = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    ''', (nuevo_estado, fabricacion_id))
                else:
                    cursor.execute('UPDATE pedidos_seguimiento SET estado = ? WHERE id = ?', 
                                 (nuevo_estado, fabricacion_id))

                conn.commit()
                return jsonify({'success': True, 'message': f'{codigo_pedido} avanzado a: {nuevo_estado.replace("_", " ").title()}'})
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener estado actual
        cursor.execute('SELECT estado, codigo_pedido FROM pedidos_seguimiento WHERE id = ?', (fabricacion_id,))
        fab = cursor.fetchone()
        
        if not fab:
            return jsonify({'success': False, 'message': 'Orden de fabricación no encontrada'})

        estado_actual = fab[0]
        codigo_pedido = fab[1]

        # Definir secuencia de estados
        estados_secuencia = ['aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa']

        try:
            indice_actual = estados_secuencia.index(estado_actual)
            if indice_actual > 0:
                nuevo_estado = estados_secuencia[indice_actual - 1]
                cursor.execute('''
                    UPDATE pedidos_seguimiento 
                    SET estado = ?, fecha_entrega_real = NULL 
                    WHERE id = ?
                ''', (nuevo_estado, fabricacion_id))

                conn.commit()
                return jsonify({'success': True, 'message': f'{codigo_pedido} retrocedido a: {nuevo_estado.replace("_", " ").title()}'})
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

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Extraer el ID numérico del event_id
        numeric_id = int(event_id.split('_')[1])

        if event_type == 'despacho':
            # Verificar permisos para despachos
            if session['user_role'] not in ['admin', 'general', 'despacho']:
                return jsonify({'success': False, 'message': 'Sin permisos para modificar despachos'})

            cursor.execute('''
                UPDATE despachos SET fecha_programada = ? WHERE id = ?
            ''', (new_start, numeric_id))

        elif event_type == 'tarea':
            cursor.execute('''
                UPDATE tareas SET fecha_programada = ? WHERE id = ?
            ''', (new_start, numeric_id))

        elif event_type == 'recordatorio':
            # Verificar permisos para recordatorios
            if session['user_role'] not in ['admin', 'general']:
                return jsonify({'success': False, 'message': 'Sin permisos para modificar recordatorios'})

            cursor.execute('''
                UPDATE recordatorios SET fecha_recordatorio = ? WHERE id = ?
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


@app.route('/api/proyectos_para_despacho')
@login_required
@role_required(['admin', 'general', 'despacho'])
def api_proyectos_para_despacho():
    """API para obtener proyectos listos para despacho"""
    conn = sqlite3.connect('mobikit.db')
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
            'id': row[0],
            'codigo': row[1] or f'PROJ-{row[0]}',
            'nombre': row[2],
            'cliente': row[3] or 'Sin cliente'
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
    conn = sqlite3.connect('mobikit.db')
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
    conn = sqlite3.connect('mobikit.db')
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
    conn = sqlite3.connect('mobikit.db')
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
    conn = sqlite3.connect('mobikit.db')
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
    conn = sqlite3.connect('mobikit.db')
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener información actual de la tarea
        cursor.execute('''
            SELECT t.estado, t.rol_asignado, t.tipo, t.etapa_fabricacion, 
                   t.proyecto_id, t.titulo, p.nombre as proyecto_nombre
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            WHERE t.id = ?
        ''', (tarea_id,))

        tarea = cursor.fetchone()
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'})

        estado_actual, rol, tipo, etapa_actual, proyecto_id, titulo, proyecto_nombre = tarea

        # Verificar permisos
        if session['user_role'] not in ['admin', 'general'] and session['user_role'] != rol:
            return jsonify({'success': False, 'message': 'Sin permisos para modificar esta tarea'})

        # Determinar siguiente estado según el rol
        if rol == 'diseñador':
            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                cursor.execute('UPDATE tareas SET estado = ?, fecha_inicio = ? WHERE id = ?', 
                             (nuevo_estado, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                nuevo_estado = 'completada'
                cursor.execute('UPDATE tareas SET estado = ?, fecha_completada = ? WHERE id = ?', 
                             (nuevo_estado, datetime.now(), tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        elif rol == 'operación':
            etapas = ['seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo']

            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                nueva_etapa = 'seccionado'
                cursor.execute('UPDATE tareas SET estado = ?, etapa_fabricacion = ?, fecha_inicio = ? WHERE id = ?', 
                             (nuevo_estado, nueva_etapa, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                if etapa_actual in etapas:
                    indice_actual = etapas.index(etapa_actual)
                    if indice_actual < len(etapas) - 1:
                        nueva_etapa = etapas[indice_actual + 1]
                        cursor.execute('UPDATE tareas SET etapa_fabricacion = ? WHERE id = ?', 
                                     (nueva_etapa, tarea_id))
                    else:
                        # Última etapa completada
                        cursor.execute('UPDATE tareas SET estado = ?, fecha_completada = ? WHERE id = ?', 
                                     ('completada', datetime.now(), tarea_id))
                        nuevo_estado = 'completada'
                else:
                    nueva_etapa = 'seccionado'
                    cursor.execute('UPDATE tareas SET etapa_fabricacion = ? WHERE id = ?', 
                                 (nueva_etapa, tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        else:  # embalaje, despacho, general
            if estado_actual == 'pendiente':
                nuevo_estado = 'en_progreso'
                cursor.execute('UPDATE tareas SET estado = ?, fecha_inicio = ? WHERE id = ?', 
                             (nuevo_estado, datetime.now(), tarea_id))
            elif estado_actual == 'en_progreso':
                nuevo_estado = 'completada'
                cursor.execute('UPDATE tareas SET estado = ?, fecha_completada = ? WHERE id = ?', 
                             (nuevo_estado, datetime.now(), tarea_id))
            else:
                return jsonify({'success': False, 'message': 'Tarea ya completada'})

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('tareas', ?, 'UPDATE', ?, ?)
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
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener información actual de la tarea
        cursor.execute('''
            SELECT t.estado, t.rol_asignado, t.tipo, t.etapa_fabricacion, 
                   t.proyecto_id, t.titulo, p.nombre as proyecto_nombre
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            WHERE t.id = ?
        ''', (tarea_id,))

        tarea = cursor.fetchone()
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'})

        estado_actual, rol, tipo, etapa_actual, proyecto_id, titulo, proyecto_nombre = tarea

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
                    cursor.execute('UPDATE tareas SET etapa_fabricacion = ? WHERE id = ?', 
                                 (nueva_etapa, tarea_id))
                else:
                    # Volver a pendiente
                    cursor.execute('UPDATE tareas SET estado = ?, etapa_fabricacion = NULL, fecha_inicio = NULL WHERE id = ?', 
                                 ('pendiente', tarea_id))
        elif estado_actual == 'completada':
            cursor.execute('UPDATE tareas SET estado = ?, fecha_completada = NULL WHERE id = ?', 
                         ('en_progreso', tarea_id))
        elif estado_actual == 'en_progreso':
            cursor.execute('UPDATE tareas SET estado = ?, fecha_inicio = NULL WHERE id = ?', 
                         ('pendiente', tarea_id))
        else:
            return jsonify({'success': False, 'message': 'No se puede retroceder más'})

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('tareas', ?, 'UPDATE', ?, ?)
        ''', (tarea_id, session['user_id'], 
              json.dumps({'accion': 'retroceder_tarea', 'titulo': titulo, 'proyecto': proyecto_nombre})))

        conn.commit()
        return jsonify({'success': True, 'message': 'Tarea retrocedida exitosamente'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al retroceder tarea: {str(e)}'})
    finally:
        conn.close()


@app.route('/nueva_orden_compra', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nueva_orden_compra():
    """Crear nueva orden de compra con múltiples categorías y pedidos de seguimiento"""
    try:
        numero_oc = request.form['numero_oc']
        proyecto_existente_id = request.form.get('proyecto_existente_id')
        cliente_id = request.form.get('cliente_id')
        nuevo_cliente_nombre = request.form.get('nuevo_cliente_nombre', '').strip()
        nombre_proyecto = request.form.get('nombre_proyecto', '').strip()
        descripcion = request.form.get('descripcion', '').strip() or None
        fecha_entrega = request.form['fecha_entrega']
        prioridad = request.form.get('prioridad', 'media')
        monto = request.form.get('monto')

        # Obtener categorías y subcategorías como arrays
        categorias_raw = request.form.get('categorias_selected', '').strip()
        subcategorias_raw = request.form.get('subcategorias_selected', '').strip()

        # Si no vienen como arrays, intentar obtener individualmente
        if not categorias_raw:
            categoria_simple = request.form.get('categoria_id')
            subcategoria_simple = request.form.get('subcategoria_id')
            if categoria_simple:
                categorias = [categoria_simple]
                subcategorias = [subcategoria_simple] if subcategoria_simple else ['']
            else:
                categorias = []
                subcategorias = []
        else:
            # Procesar arrays JSON
            try:
                import json
                categorias = json.loads(categorias_raw) if categorias_raw else []
                subcategorias = json.loads(subcategorias_raw) if subcategorias_raw else []
            except:
                categorias = categorias_raw.split(',') if categorias_raw else []
                subcategorias = subcategorias_raw.split(',') if subcategorias_raw else []

        # Validar que hay al menos una categoría
        if not categorias or not any(cat for cat in categorias if cat and cat != ''):
            flash('Debe seleccionar al menos una categoría', 'error')
            return redirect(url_for('dashboard'))

        # Validar monto
        monto_float = None
        if monto:
            try:
                monto_float = float(monto)
            except ValueError:
                flash('Monto inválido', 'error')
                return redirect(url_for('dashboard'))

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Manejar cliente
        if cliente_id == 'nuevo':
            if not nuevo_cliente_nombre:
                flash('Debe especificar el nombre del nuevo cliente', 'error')
                return redirect(url_for('dashboard'))

            # Crear nuevo cliente
            cursor.execute('''
                INSERT INTO clientes (nombre, activo) VALUES (?, ?)
            ''', (nuevo_cliente_nombre, True))
            cliente_id = cursor.lastrowid
        else:
            # Verificar que el cliente existe
            cursor.execute('SELECT nombre FROM clientes WHERE id = ? AND activo = TRUE', (cliente_id,))
            if not cursor.fetchone():
                flash('Cliente no válido', 'error')
                return redirect(url_for('dashboard'))

        # Manejar proyecto
        if proyecto_existente_id == 'nuevo':
            if not nombre_proyecto:
                flash('Debe especificar el nombre del nuevo proyecto', 'error')
                return redirect(url_for('dashboard'))

            # Crear nuevo proyecto
            cursor.execute('''
                INSERT INTO proyectos (
                    codigo, nombre, cliente_id, descripcion, estado, prioridad, 
                    fecha_inicio, fecha_entrega, presupuesto
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (numero_oc, nombre_proyecto, cliente_id, descripcion, 'en_desarrollo', 
                  prioridad, datetime.now().date(), fecha_entrega, monto_float))
            proyecto_id = cursor.lastrowid
        else:
            proyecto_id = proyecto_existente_id
            # Verificar que el proyecto existe y pertenece al cliente
            cursor.execute('SELECT nombre FROM proyectos WHERE id = ? AND cliente_id = ?', (proyecto_id, cliente_id))
            if not cursor.fetchone():
                flash('Proyecto no válido para el cliente seleccionado', 'error')
                return redirect(url_for('dashboard'))

        # Crear relaciones de categorías y pedidos de seguimiento
        for i, categoria_id in enumerate(categorias):
            if categoria_id:  # Solo procesar categorías válidas
                subcategoria_id = subcategorias[i] if i < len(subcategorias) and subcategorias[i] else None

                # Verificar que la categoría existe
                cursor.execute('SELECT nombre FROM categorias_producto WHERE id = ? AND activo = TRUE', (categoria_id,))
                categoria_info = cursor.fetchone()
                if not categoria_info:
                    continue

                # Verificar subcategoría si se proporciona
                if subcategoria_id:
                    cursor.execute('SELECT nombre FROM subcategorias_producto WHERE id = ? AND activo = TRUE', (subcategoria_id,))
                    subcategoria_info = cursor.fetchone()
                    if not subcategoria_info:
                        subcategoria_id = None

                # Insertar relación proyecto-categoría
                cursor.execute('''
                    INSERT OR IGNORE INTO proyecto_categorias (proyecto_id, categoria_id, subcategoria_id)
                    VALUES (?, ?, ?)
                ''', (proyecto_id, categoria_id, subcategoria_id))

                # Crear pedido de seguimiento
                cursor.execute('SELECT COUNT(*) FROM pedidos_seguimiento WHERE SUBSTRING(codigo_pedido, 1, 13) = ?', 
                             (f"PED-{datetime.now().year}-",))
                pedido_numero = cursor.fetchone()[0] + 1
                codigo_pedido = f"PED-{datetime.now().year}-{pedido_numero:04d}"

                # Obtener nombres para el pedido
                cursor.execute('SELECT nombre FROM categorias_producto WHERE id = ?', (categoria_id,))
                categoria_nombre = cursor.fetchone()[0]

                nombre_pedido = f"{categoria_nombre}"
                if subcategoria_id:
                    cursor.execute('SELECT nombre FROM subcategorias_producto WHERE id = ?', (subcategoria_id,))
                    subcategoria_nombre = cursor.fetchone()[0]
                    nombre_pedido += f" - {subcategoria_nombre}"

                cursor.execute('''
                    INSERT INTO pedidos_seguimiento (
                        proyecto_id, categoria_id, subcategoria_id, codigo_pedido, 
                        nombre, estado, fecha_inicio, fecha_entrega_estimada
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (proyecto_id, categoria_id, subcategoria_id, codigo_pedido,
                      nombre_pedido, 'en_desarrollo', datetime.now().date(), fecha_entrega))

        conn.commit()
        conn.close()

        flash(f'Orden de compra {numero_oc} creada exitosamente con pedidos de seguimiento', 'success')
        return redirect(url_for('proyecto_detalle', proyecto_id=proyecto_id))

    except sqlite3.IntegrityError as e:
        if 'codigo' in str(e).lower():
            flash('Ya existe una orden con ese número', 'error')
        else:
            flash('Error de datos duplicados', 'error')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error al crear orden de compra: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/api/clientes_activos')
@login_required
def api_clientes_activos():
    """API para obtener clientes activos"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, nombre FROM clientes WHERE activo = TRUE ORDER BY nombre ASC')
    clientes = [{'id': row[0], 'nombre': row[1]} for row in cursor.fetchall()]

    conn.close()
    return jsonify(clientes)


@app.route('/api/categorias')
@login_required
def api_categorias():
    """API para obtener categorías de productos"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, nombre, color FROM categorias_producto WHERE activo = TRUE ORDER BY nombre ASC')
    categorias = [{'id': row[0], 'nombre': row[1], 'color': row[2]} for row in cursor.fetchall()]

    conn.close()
    return jsonify(categorias)


@app.route('/api/subcategorias/<int:categoria_id>')
@login_required
def api_subcategorias(categoria_id):
    """API para obtener subcategorías de una categoría específica"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, nombre FROM subcategorias_producto 
        WHERE categoria_id = ? AND activo = TRUE 
        ORDER BY nombre ASC
    ''', (categoria_id,))
    subcategorias = [{'id': row[0], 'nombre': row[1]} for row in cursor.fetchall()]

    conn.close()
    return jsonify(subcategorias)


@app.route('/api/proyectos_cliente/<int:cliente_id>')
@login_required
def api_proyectos_cliente(cliente_id):
    """API para obtener proyectos de un cliente específico"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, codigo, nombre FROM proyectos 
        WHERE cliente_id = ? AND estado NOT IN ('entregado', 'cancelado')
        ORDER BY created_at DESC
    ''', (cliente_id,))
    proyectos = [{'id': row[0], 'codigo': row[1], 'nombre': row[2]} for row in cursor.fetchall()]

    conn.close()
    return jsonify(proyectos)


@app.route('/api/proyectos_disponibles_fabricacion')
@login_required
def api_proyectos_disponibles_fabricacion():
    """API para obtener proyectos disponibles para órdenes de fabricación"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.id, p.codigo, p.nombre, c.nombre as cliente_nombre
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE p.estado IN ('en_desarrollo', 'diseño')
        ORDER BY p.created_at DESC
    ''')
    
    proyectos = []
    for row in cursor.fetchall():
        proyectos.append({
            'id': row[0],
            'codigo': row[1],
            'nombre': row[2],
            'cliente': row[3] or 'Sin cliente'
        })

    conn.close()
    return jsonify(proyectos)


@app.route('/api/categorias_proyecto/<int:proyecto_id>')
@login_required
def api_categorias_proyecto(proyecto_id):
    """API para obtener categorías de un proyecto específico"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT pc.categoria_id, pc.subcategoria_id, cat.nombre as categoria_nombre, 
               subcat.nombre as subcategoria_nombre
        FROM proyecto_categorias pc
        JOIN categorias_producto cat ON pc.categoria_id = cat.id
        LEFT JOIN subcategorias_producto subcat ON pc.subcategoria_id = subcat.id
        WHERE pc.proyecto_id = ?
        ORDER BY cat.nombre, subcat.nombre
    ''', (proyecto_id,))
    
    categorias = []
    for row in cursor.fetchall():
        categorias.append({
            'categoria_id': row[0],
            'subcategoria_id': row[1],
            'categoria_nombre': row[2],
            'subcategoria_nombre': row[3]
        })

    conn.close()
    return jsonify(categorias)


@app.route('/crear_orden_fabricacion', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def crear_orden_fabricacion():
    """Crear nueva orden de fabricación"""
    try:
        proyecto_id = request.form['proyecto_id']
        tipo_orden = request.form['tipo_orden']
        fecha_entrega_estimada = request.form['fecha_entrega_estimada']
        cantidad_tableros = int(request.form['cantidad_tableros'])
        observaciones = request.form.get('observaciones', '').strip() or None
        categorias_seleccionadas = request.form.getlist('categorias_seleccionadas')

        if not categorias_seleccionadas:
            flash('Debe seleccionar al menos una categoría', 'error')
            return redirect(url_for('ordenes_fabricacion'))

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar que el proyecto existe
        cursor.execute('SELECT codigo, nombre FROM proyectos WHERE id = ?', (proyecto_id,))
        proyecto = cursor.fetchone()
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('ordenes_fabricacion'))

        # Generar código único para la orden de fabricación
        cursor.execute('SELECT COUNT(*) FROM ordenes_fabricacion WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
        orden_numero = cursor.fetchone()[0] + 1
        codigo_orden = f"OF-{datetime.now().year}-{orden_numero:04d}"

        # Crear orden de fabricación
        cursor.execute('''
            INSERT INTO ordenes_fabricacion (
                codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada, 
                cantidad_tableros, observaciones, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada, 
              cantidad_tableros, observaciones, 'pendiente'))

        orden_fabricacion_id = cursor.lastrowid

        # Crear relaciones de categorías
        for categoria_str in categorias_seleccionadas:
            categoria_id, subcategoria_id = categoria_str.split(',')
            subcategoria_id = subcategoria_id if subcategoria_id else None

            cursor.execute('''
                INSERT INTO orden_fabricacion_categorias (
                    orden_fabricacion_id, categoria_id, subcategoria_id
                ) VALUES (?, ?, ?)
            ''', (orden_fabricacion_id, categoria_id, subcategoria_id))

            # Crear pedido de seguimiento
            cursor.execute('SELECT COUNT(*) FROM pedidos_seguimiento WHERE SUBSTRING(codigo_pedido, 1, 13) = ?', 
                         (f"PED-{datetime.now().year}-",))
            pedido_numero = cursor.fetchone()[0] + 1
            codigo_pedido = f"PED-{datetime.now().year}-{pedido_numero:04d}"

            # Obtener nombres para el pedido
            cursor.execute('SELECT nombre FROM categorias_producto WHERE id = ?', (categoria_id,))
            categoria_nombre = cursor.fetchone()[0]

            nombre_pedido = f"{codigo_orden} - {categoria_nombre}"
            if subcategoria_id:
                cursor.execute('SELECT nombre FROM subcategorias_producto WHERE id = ?', (subcategoria_id,))
                subcategoria_nombre = cursor.fetchone()[0]
                nombre_pedido += f" - {subcategoria_nombre}"

            cursor.execute('''
                INSERT INTO pedidos_seguimiento (
                    proyecto_id, orden_fabricacion_id, categoria_id, subcategoria_id, 
                    codigo_pedido, nombre, estado, fecha_entrega_estimada
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (proyecto_id, orden_fabricacion_id, categoria_id, subcategoria_id,
                  codigo_pedido, nombre_pedido, 'pendiente', fecha_entrega_estimada))

        conn.commit()
        conn.close()

        flash(f'Orden de fabricación {codigo_orden} creada exitosamente', 'success')
        return redirect(url_for('ordenes_fabricacion'))

    except Exception as e:
        flash(f'Error al crear orden de fabricación: {str(e)}', 'error')
        return redirect(url_for('ordenes_fabricacion'))


@app.route('/crear_orden_fabricacion_desde_oc', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación'])
def crear_orden_fabricacion_desde_oc():
    """Crear orden de fabricación desde orden de compra y cambiar estado a 'En proceso'"""
    try:
        proyecto_id = request.form['proyecto_id']
        tipo_orden = request.form['tipo_orden']
        fecha_entrega_estimada = request.form['fecha_entrega_estimada']
        cantidad_tableros = int(request.form['cantidad_tableros'])
        observaciones = request.form.get('observaciones', '').strip() or None
        categorias_seleccionadas = request.form.getlist('categorias_seleccionadas')

        if not categorias_seleccionadas:
            flash('Debe seleccionar al menos una categoría', 'error')
            return redirect(url_for('ordenes_compra'))

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar que el proyecto existe y está pendiente
        cursor.execute('SELECT codigo, nombre, estado FROM proyectos WHERE id = ?', (proyecto_id,))
        proyecto = cursor.fetchone()
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('ordenes_compra'))

        if proyecto[2] not in ['en_desarrollo', 'diseño']:
            flash('El proyecto no está en estado pendiente', 'error')
            return redirect(url_for('ordenes_compra'))

        # Generar código único para la orden de fabricación
        cursor.execute('SELECT COUNT(*) FROM ordenes_fabricacion WHERE strftime("%Y", created_at) = strftime("%Y", "now")')
        orden_numero = cursor.fetchone()[0] + 1
        codigo_orden = f"OF-{datetime.now().year}-{orden_numero:04d}"

        # Crear orden de fabricación
        cursor.execute('''
            INSERT INTO ordenes_fabricacion (
                codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada, 
                cantidad_tableros, observaciones, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (codigo_orden, proyecto_id, tipo_orden, fecha_entrega_estimada, 
              cantidad_tableros, observaciones, 'pendiente'))

        orden_fabricacion_id = cursor.lastrowid

        # Crear relaciones de categorías y pedidos de seguimiento
        for categoria_str in categorias_seleccionadas:
            categoria_id, subcategoria_id = categoria_str.split(',')
            subcategoria_id = subcategoria_id if subcategoria_id else None

            cursor.execute('''
                INSERT INTO orden_fabricacion_categorias (
                    orden_fabricacion_id, categoria_id, subcategoria_id
                ) VALUES (?, ?, ?)
            ''', (orden_fabricacion_id, categoria_id, subcategoria_id))

            # Crear pedido de seguimiento
            cursor.execute('SELECT COUNT(*) FROM pedidos_seguimiento WHERE SUBSTRING(codigo_pedido, 1, 13) = ?', 
                         (f"PED-{datetime.now().year}-",))
            pedido_numero = cursor.fetchone()[0] + 1
            codigo_pedido = f"PED-{datetime.now().year}-{pedido_numero:04d}"

            # Obtener nombres para el pedido
            cursor.execute('SELECT nombre FROM categorias_producto WHERE id = ?', (categoria_id,))
            categoria_nombre = cursor.fetchone()[0]

            nombre_pedido = f"{codigo_orden} - {categoria_nombre}"
            if subcategoria_id:
                cursor.execute('SELECT nombre FROM subcategorias_producto WHERE id = ?', (subcategoria_id,))
                subcategoria_nombre = cursor.fetchone()[0]
                nombre_pedido += f" - {subcategoria_nombre}"

            cursor.execute('''
                INSERT INTO pedidos_seguimiento (
                    proyecto_id, orden_fabricacion_id, categoria_id, subcategoria_id, 
                    codigo_pedido, nombre, estado, fecha_entrega_estimada
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (proyecto_id, orden_fabricacion_id, categoria_id, subcategoria_id,
                  codigo_pedido, nombre_pedido, 'pendiente', fecha_entrega_estimada))

        # Cambiar estado del proyecto a "En proceso"
        cursor.execute('''
            UPDATE proyectos 
            SET estado = 'aprobado_produccion', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (proyecto_id,))

        conn.commit()
        conn.close()

        flash(f'Orden de fabricación {codigo_orden} creada. Proyecto cambió a estado "En proceso"', 'success')
        return redirect(url_for('ordenes_compra'))

    except Exception as e:
        flash(f'Error al crear orden de fabricación: {str(e)}', 'error')
        return redirect(url_for('ordenes_compra'))


@app.route('/avanzar_estado_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'operación', 'embalaje'])
def avanzar_estado_proyecto(proyecto_id):
    """Avanzar estado de proyecto según los estados de fábrica"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener estado actual del proyecto
        cursor.execute('SELECT estado, nombre, codigo FROM proyectos WHERE id = ?', (proyecto_id,))
        proyecto = cursor.fetchone()

        if not proyecto:
            return jsonify({'success': False, 'message': 'Proyecto no encontrado'})

        estado_actual, nombre_proyecto, codigo_proyecto = proyecto

        # Definir secuencia de estados con nombres descriptivos
        estados_secuencia = [
            ('en_desarrollo', 'En Desarrollo'),
            ('aprobado_produccion', 'Aprobado para Producción'), 
            ('seccionado', 'Seccionado'),
            ('enchapado', 'Enchapado'),
            ('mecanizado', 'Mecanizado'),
            ('produccion_completa', 'Producción P&P Lista'),
            ('embalando', 'Embalando'),
            ('listo_despacho', 'Listo para Despacho'),
            ('entregado', 'Despachado')
        ]

        # Buscar el estado actual en la secuencia
        indice_actual = -1
        for i, (estado, nombre) in enumerate(estados_secuencia):
            if estado == estado_actual:
                indice_actual = i
                break

        if indice_actual == -1:
            return jsonify({'success': False, 'message': f'Estado actual "{estado_actual}" no válido'})

        if indice_actual < len(estados_secuencia) - 1:
            nuevo_estado, nuevo_nombre = estados_secuencia[indice_actual + 1]

            cursor.execute('UPDATE proyectos SET estado = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                         (nuevo_estado, proyecto_id))

            if cursor.rowcount > 0:
                # También actualizar pedidos de seguimiento relacionados si existen
                cursor.execute('''
                    UPDATE pedidos_seguimiento 
                    SET estado = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE proyecto_id = ? AND estado != 'entregado'
                ''', (nuevo_estado, proyecto_id))

                # Registrar en auditoría
                cursor.execute('''
                    INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
                    VALUES ('proyectos', ?, 'UPDATE', ?, ?)
                ''', (proyecto_id, session['user_id'], 
                      json.dumps({
                          'accion': 'avanzar_estado', 
                          'estado_anterior': estado_actual, 
                          'estado_nuevo': nuevo_estado,
                          'proyecto': codigo_proyecto
                      })))

                conn.commit()
                return jsonify({
                    'success': True, 
                    'message': f'Proyecto {codigo_proyecto} avanzado a: {nuevo_nombre}'
                })
            else:
                return jsonify({'success': False, 'message': 'No se pudo actualizar el proyecto'})
        else:
            return jsonify({'success': False, 'message': 'El proyecto ya está en el estado final'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Error al avanzar estado: {str(e)}'})
    finally:
        conn.close()


@app.route('/gestion_pedidos')
@login_required
def gestion_pedidos():
    """Vista principal de gestión de pedidos con estados secuenciales"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Estados secuenciales obligatorios
    estados_secuencia = [
        ('en_desarrollo', 'Diseño', 'diseñador'),
        ('aprobado_produccion', 'Aprobado Producción', 'general'),
        ('seccionado', 'Seccionado', 'operación'),
        ('enchapado', 'Enchapado', 'operación'),
        ('mecanizado', 'Mecanizado', 'operación'),
        ('produccion_completa', 'Producción P&P Lista', 'operación'),
        ('embalando', 'Embalando', 'embalaje'),
        ('listo_despacho', 'Listo Despacho', 'despacho'),
        ('entregado', 'Despachado', 'despacho')
    ]

    # Obtener pedidos de seguimiento con información del proyecto y cliente
    user_role = session['user_role']
    
    if user_role == 'admin':
        # Admin ve todos los pedidos
        cursor.execute('''
            SELECT ps.id, ps.codigo_pedido, ps.nombre, ps.estado, ps.fecha_inicio, 
                   ps.fecha_entrega_estimada, p.codigo as proyecto_codigo, p.nombre as proyecto_nombre,
                   c.nombre as cliente_nombre, ps.categoria_id, ps.subcategoria_id,
                   julianday(ps.fecha_entrega_estimada) - julianday('now') as dias_restantes
            FROM pedidos_seguimiento ps
            JOIN proyectos p ON ps.proyecto_id = p.id
            LEFT JOIN clientes c ON p.cliente_id = c.id
            WHERE ps.estado != 'entregado'
            ORDER BY 
                CASE ps.estado
                    WHEN 'en_desarrollo' THEN 1
                    WHEN 'aprobado_produccion' THEN 2
                    WHEN 'seccionado' THEN 3
                    WHEN 'enchapado' THEN 4
                    WHEN 'mecanizado' THEN 5
                    WHEN 'produccion_completa' THEN 6
                    WHEN 'embalando' THEN 7
                    WHEN 'listo_despacho' THEN 8
                    ELSE 9
                END,
                ps.fecha_entrega_estimada ASC
        ''')
    else:
        # Filtrar por rol - cada rol ve los pedidos que le corresponden o están próximos
        roles_estados = {
            'diseñador': ['en_desarrollo'],
            'general': ['en_desarrollo', 'aprobado_produccion'],
            'operación': ['aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa'],
            'embalaje': ['produccion_completa', 'embalando'],
            'despacho': ['embalando', 'listo_despacho']
        }
        
        estados_permitidos = roles_estados.get(user_role, [])
        if estados_permitidos:
            placeholders = ','.join(['?' for _ in estados_permitidos])
            cursor.execute(f'''
                SELECT ps.id, ps.codigo_pedido, ps.nombre, ps.estado, ps.fecha_inicio, 
                       ps.fecha_entrega_estimada, p.codigo as proyecto_codigo, p.nombre as proyecto_nombre,
                       c.nombre as cliente_nombre, ps.categoria_id, ps.subcategoria_id,
                       julianday(ps.fecha_entrega_estimada) - julianday('now') as dias_restantes
                FROM pedidos_seguimiento ps
                JOIN proyectos p ON ps.proyecto_id = p.id
                LEFT JOIN clientes c ON p.cliente_id = c.id
                WHERE ps.estado IN ({placeholders})
                ORDER BY 
                    CASE ps.estado
                        WHEN 'en_desarrollo' THEN 1
                        WHEN 'aprobado_produccion' THEN 2
                        WHEN 'seccionado' THEN 3
                        WHEN 'enchapado' THEN 4
                        WHEN 'mecanizado' THEN 5
                        WHEN 'produccion_completa' THEN 6
                        WHEN 'embalando' THEN 7
                        WHEN 'listo_despacho' THEN 8
                        ELSE 9
                    END,
                    ps.fecha_entrega_estimada ASC
            ''', estados_permitidos)
        else:
            cursor.execute('SELECT NULL LIMIT 0')  # No hay resultados

    pedidos = cursor.fetchall()

    # Agrupar pedidos por estado para la vista
    pedidos_por_estado = {}
    for estado, nombre_estado, rol_responsable in estados_secuencia:
        pedidos_por_estado[estado] = {
            'nombre': nombre_estado,
            'rol_responsable': rol_responsable,
            'pedidos': []
        }

    for pedido in pedidos:
        estado = pedido[3]
        if estado in pedidos_por_estado:
            pedidos_por_estado[estado]['pedidos'].append(pedido)

    conn.close()

    return render_template('gestion_pedidos.html', 
                         pedidos_por_estado=pedidos_por_estado,
                         estados_secuencia=estados_secuencia,
                         user_role=user_role)


@app.route('/avanzar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def avanzar_pedido(pedido_id):
    """Avanzar un pedido al siguiente estado en la secuencia"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener información del pedido
        cursor.execute('''
            SELECT ps.estado, ps.codigo_pedido, ps.nombre, p.nombre as proyecto_nombre
            FROM pedidos_seguimiento ps
            JOIN proyectos p ON ps.proyecto_id = p.id
            WHERE ps.id = ?
        ''', (pedido_id,))

        pedido = cursor.fetchone()
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'})

        estado_actual, codigo_pedido, nombre_pedido, proyecto_nombre = pedido

        # Estados secuenciales
        estados_secuencia = [
            ('en_desarrollo', 'diseñador'),
            ('aprobado_produccion', 'general'),
            ('seccionado', 'operación'),
            ('enchapado', 'operación'),
            ('mecanizado', 'operación'),
            ('produccion_completa', 'operación'),
            ('embalando', 'embalaje'),
            ('listo_despacho', 'despacho'),
            ('entregado', 'despacho')
        ]

        # Verificar permisos según el estado actual
        rol_actual = None
        for i, (estado, rol) in enumerate(estados_secuencia):
            if estado == estado_actual:
                rol_actual = rol
                break

        if session['user_role'] not in ['admin', 'general'] and session['user_role'] != rol_actual:
            return jsonify({'success': False, 'message': 'Sin permisos para avanzar este pedido'})

        # Encontrar siguiente estado
        siguiente_estado = None
        for i, (estado, rol) in enumerate(estados_secuencia):
            if estado == estado_actual and i < len(estados_secuencia) - 1:
                siguiente_estado = estados_secuencia[i + 1][0]
                break

        if not siguiente_estado:
            return jsonify({'success': False, 'message': 'El pedido ya está en el estado final'})

        # Actualizar estado del pedido
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (siguiente_estado, pedido_id))

        # Si es el último estado, marcar fecha de entrega real
        if siguiente_estado == 'entregado':
            cursor.execute('''
                UPDATE pedidos_seguimiento 
                SET fecha_entrega_real = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (pedido_id,))

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('pedidos_seguimiento', ?, 'UPDATE', ?, ?)
        ''', (pedido_id, session['user_id'], 
              json.dumps({
                  'accion': 'avanzar_pedido',
                  'estado_anterior': estado_actual,
                  'estado_nuevo': siguiente_estado,
                  'codigo_pedido': codigo_pedido
              })))

        conn.commit()
        return jsonify({
            'success': True, 
            'message': f'Pedido {codigo_pedido} avanzado a: {siguiente_estado.replace("_", " ").title()}'
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al avanzar pedido: {str(e)}'})
    finally:
        conn.close()


@app.route('/retroceder_pedido/<int:pedido_id>', methods=['POST'])
@login_required
@role_required(['admin', 'general'])
def retroceder_pedido(pedido_id):
    """Retroceder un pedido al estado anterior (solo admin/general)"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Obtener información del pedido
        cursor.execute('''
            SELECT ps.estado, ps.codigo_pedido
            FROM pedidos_seguimiento ps
            WHERE ps.id = ?
        ''', (pedido_id,))

        pedido = cursor.fetchone()
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'})

        estado_actual, codigo_pedido = pedido

        # Estados secuenciales
        estados_secuencia = [
            'en_desarrollo', 'aprobado_produccion', 'seccionado', 'enchapado', 
            'mecanizado', 'produccion_completa', 'embalando', 'listo_despacho', 'entregado'
        ]

        # Encontrar estado anterior
        estado_anterior = None
        for i, estado in enumerate(estados_secuencia):
            if estado == estado_actual and i > 0:
                estado_anterior = estados_secuencia[i - 1]
                break

        if not estado_anterior:
            return jsonify({'success': False, 'message': 'No se puede retroceder más'})

        # Actualizar estado del pedido
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = ?, updated_at = CURRENT_TIMESTAMP, fecha_entrega_real = NULL
            WHERE id = ?
        ''', (estado_anterior, pedido_id))

        # Registrar en auditoría
        cursor.execute('''
            INSERT INTO auditoria (tabla_afectada, registro_id, accion, usuario_id, valores_nuevos)
            VALUES ('pedidos_seguimiento', ?, 'UPDATE', ?, ?)
        ''', (pedido_id, session['user_id'], 
              json.dumps({
                  'accion': 'retroceder_pedido',
                  'estado_anterior': estado_actual,
                  'estado_nuevo': estado_anterior,
                  'codigo_pedido': codigo_pedido
              })))

        conn.commit()
        return jsonify({
            'success': True, 
            'message': f'Pedido {codigo_pedido} retrocedido a: {estado_anterior.replace("_", " ").title()}'
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al retroceder pedido: {str(e)}'})
    finally:
        conn.close()


@app.route('/reportes')
@login_required
@role_required(['admin', 'general'])
def reportes():
    conn = sqlite3.connect('mobikit.db')
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