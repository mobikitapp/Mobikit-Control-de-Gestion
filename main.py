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

    # Estadísticas generales
    cursor.execute('SELECT COUNT(*) FROM proyectos')
    total_proyectos = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM tareas WHERE estado = "pendiente"')
    tareas_pendientes = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM tareas WHERE estado = "completada"')
    tareas_completadas = cursor.fetchone()[0]

    # Tareas asignadas al usuario actual o su rol
    cursor.execute(
        '''
        SELECT t.id, t.titulo, p.nombre as proyecto, t.fecha_programada, t.estado
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        WHERE t.usuario_asignado_id = ? OR t.rol_asignado = ?
        ORDER BY t.fecha_programada ASC
        LIMIT 10
    ''', (session['user_id'], session['user_role']))
    mis_tareas = cursor.fetchall()

    # Proyectos recientes
    cursor.execute('''
        SELECT p.id, p.nombre, c.nombre as cliente, p.estado, p.fecha_entrega
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        ORDER BY p.created_at DESC
        LIMIT 5
    ''')
    proyectos_recientes = cursor.fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_proyectos=total_proyectos,
                           tareas_pendientes=tareas_pendientes,
                           tareas_completadas=tareas_completadas,
                           mis_tareas=mis_tareas,
                           proyectos_recientes=proyectos_recientes)


@app.route('/clientes')
@login_required
def clientes():
    """Gestión de clientes"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*, COUNT(p.id) as total_proyectos
        FROM clientes c
        LEFT JOIN proyectos p ON c.id = p.cliente_id
        WHERE c.activo = TRUE
        GROUP BY c.id
        ORDER BY c.nombre ASC
    ''')
    clientes_list = cursor.fetchall()
    conn.close()

    return render_template('clientes.html', clientes=clientes_list)


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
        
        proyectos = cursor.fetchall()
        
        for proyecto in proyectos:
            proyecto_info = {
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
            cliente_info['proyectos'].append(proyecto_info)
        
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
            return redirect(url_for('proyectos'))
            
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
        ''', (codigo_proyecto, nombre, cliente_id, descripcion, 'diseño', prioridad,
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
        return redirect(url_for('proyecto_detalle', proyecto_id=proyecto_id))
        
    except Exception as e:
        flash(f'Error al crear proyecto: {str(e)}', 'error')
        return redirect(url_for('proyectos'))


@app.route('/tareas')
@login_required
def tareas():
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    # Filtrar tareas según el rol del usuario
    if session['user_role'] == 'admin':
        cursor.execute('''
            SELECT t.id, t.titulo, p.nombre as proyecto, t.rol_asignado, 
                   t.fecha_programada, t.estado, u.nombre as asignado
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
            ORDER BY t.fecha_programada ASC
        ''')
    else:
        cursor.execute(
            '''
            SELECT t.id, t.titulo, p.nombre as proyecto, t.rol_asignado, 
                   t.fecha_programada, t.estado, u.nombre as asignado
            FROM tareas t
            JOIN proyectos p ON t.proyecto_id = p.id
            LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
            WHERE t.rol_asignado = ? OR t.usuario_asignado_id = ?
            ORDER BY t.fecha_programada ASC
        ''', (session['user_role'], session['user_id']))

    tareas_list = cursor.fetchall()
    conn.close()

    return render_template('tareas.html', tareas=tareas_list)


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
            # Verificar que el proyecto existe y obtener su información
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


@app.route('/api/proyectos_cliente/<int:cliente_id>')
@login_required
@role_required(['admin', 'general', 'despacho'])
def api_proyectos_cliente(cliente_id):
    """API para obtener proyectos de un cliente específico"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, codigo, nombre, estado
        FROM proyectos
        WHERE cliente_id = ? AND estado NOT IN ('entregado', 'cancelado')
        ORDER BY nombre
    ''', (cliente_id,))
    
    proyectos = []
    for row in cursor.fetchall():
        proyectos.append({
            'id': row[0],
            'codigo': row[1] or f'PROJ-{row[0]}',
            'nombre': row[2],
            'estado': row[3]
        })
    
    conn.close()
    return jsonify(proyectos)

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
    """API para obtener eventos del calendario"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    events = []
    
    # Obtener despachos
    cursor.execute('''
        SELECT d.id, d.codigo_despacho, d.fecha_programada, d.estado,
               p.nombre as proyecto_nombre, c.nombre as cliente_nombre,
               d.direccion_entrega
        FROM despachos d
        JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        WHERE d.fecha_programada IS NOT NULL
    ''')
    
    for row in cursor.fetchall():
        events.append({
            'id': f'despacho_{row[0]}',
            'title': f'Despacho: {row[1]}',
            'start': row[2],
            'type': 'despacho',
            'backgroundColor': '#dc3545',
            'borderColor': '#dc3545',
            'proyecto': row[4],
            'cliente': row[5],
            'direccion': row[6],
            'estado': row[3]
        })
    
    # Obtener tareas
    cursor.execute('''
        SELECT t.id, t.titulo, t.fecha_programada, t.estado, t.descripcion,
               p.nombre as proyecto_nombre, u.nombre as usuario_nombre,
               t.rol_asignado
        FROM tareas t
        LEFT JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.fecha_programada IS NOT NULL
    ''')
    
    for row in cursor.fetchall():
        events.append({
            'id': f'tarea_{row[0]}',
            'title': f'Tarea: {row[1]}',
            'start': row[2],
            'type': 'tarea',
            'backgroundColor': '#28a745',
            'borderColor': '#28a745',
            'proyecto': row[5],
            'asignado': row[6],
            'rol_asignado': row[7],
            'estado': row[3],
            'descripcion': row[4]
        })
    
    # Obtener recordatorios
    cursor.execute('''
        SELECT r.id, r.titulo, r.fecha_recordatorio, r.mensaje, r.enviado,
               u.nombre as usuario_nombre, a.nombre as area_nombre
        FROM recordatorios r
        LEFT JOIN usuarios u ON r.usuario_id = u.id
        LEFT JOIN areas a ON r.area_id = a.id
        WHERE r.activo = TRUE AND r.fecha_recordatorio IS NOT NULL
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
