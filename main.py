from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'mobikit_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Crear carpeta de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('templates', exist_ok=True)

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


@app.route('/proyectos')
@login_required
def proyectos():
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.nombre, c.nombre as cliente, p.estado, p.fecha_entrega, u.nombre as diseñador
        FROM proyectos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        LEFT JOIN usuarios u ON p.diseñador_id = u.id
        ORDER BY p.created_at DESC
    ''')
    proyectos_list = cursor.fetchall()
    conn.close()

    return render_template('proyectos.html', proyectos=proyectos_list)


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


@app.route('/nuevo_proyecto', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nuevo_proyecto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        cliente_nombre = request.form['cliente']
        descripcion = request.form['descripcion']
        fecha_entrega = request.form['fecha_entrega']

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        
        # Create or get client
        cursor.execute('SELECT id FROM clientes WHERE nombre = ?', (cliente_nombre,))
        cliente = cursor.fetchone()
        if not cliente:
            cursor.execute('INSERT INTO clientes (nombre) VALUES (?)', (cliente_nombre,))
            cliente_id = cursor.lastrowid
        else:
            cliente_id = cliente[0]
            
        cursor.execute(
            '''
            INSERT INTO proyectos (nombre, cliente_id, descripcion, fecha_entrega, diseñador_id, fecha_inicio)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nombre, cliente_id, descripcion, fecha_entrega, session['user_id'],
              datetime.now().date()))

        proyecto_id = cursor.lastrowid

        # Crear tareas automáticas del ciclo de vida
        tareas_ciclo = [
            ('Diseño inicial', 'Crear diseño y planos del mueble', 'diseñador',
             1),
            ('Revisión de diseño', 'Revisar y aprobar diseño', 'general', 3),
            ('Planificación de producción',
             'Planificar proceso de fabricación', 'operación', 5),
            ('Fabricación', 'Fabricar el mueble según especificaciones',
             'operación', 15),
            ('Control de calidad', 'Revisar calidad del producto terminado',
             'operación', 18),
            ('Embalaje', 'Embalar producto para despacho', 'embalaje', 20),
            ('Preparación de despacho',
             'Preparar documentos y coordinar entrega', 'despacho', 22),
            ('Entrega', 'Entregar producto al cliente', 'despacho', 24)
        ]

        fecha_base = datetime.now().date()
        for titulo, descripcion, rol, dias in tareas_ciclo:
            fecha_programada = fecha_base + timedelta(days=dias)
            cursor.execute(
                '''
                INSERT INTO tareas (proyecto_id, titulo, descripcion, rol_asignado, fecha_programada)
                VALUES (?, ?, ?, ?, ?)
            ''', (proyecto_id, titulo, descripcion, rol, fecha_programada))

        conn.commit()
        conn.close()

        flash('Proyecto creado exitosamente', 'success')
        return redirect(url_for('proyecto_detalle', proyecto_id=proyecto_id))

    return render_template('nuevo_proyecto.html')


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


@app.route('/programar_despacho', methods=['POST'])
@login_required
@role_required(['admin', 'general', 'despacho'])
def programar_despacho():
    """
    Endpoint para programar despachos y crear recordatorios automáticos
    """
    try:
        proyecto_id = request.form.get('proyecto_id')
        fecha_programada = request.form.get('fecha_programada')
        transportista = request.form.get('transportista', '')
        conductor = request.form.get('conductor', '')
        telefono_conductor = request.form.get('telefono_conductor', '')
        vehiculo_patente = request.form.get('vehiculo_patente', '')
        direccion_entrega = request.form.get('direccion_entrega')
        observaciones = request.form.get('observaciones', '')

        if not all([proyecto_id, fecha_programada, direccion_entrega]):
            flash('Faltan datos obligatorios para programar el despacho', 'error')
            return redirect(request.referrer or url_for('proyectos'))

        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()

        # Verificar que el proyecto existe y obtener información
        cursor.execute('''
            SELECT p.id, p.nombre, p.codigo, c.nombre as cliente_nombre
            FROM proyectos p
            LEFT JOIN clientes c ON p.cliente_id = c.id
            WHERE p.id = ?
        ''', (proyecto_id,))
        proyecto = cursor.fetchone()

        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            conn.close()
            return redirect(request.referrer or url_for('proyectos'))

        # Generar código único para el despacho
        cursor.execute('SELECT COUNT(*) FROM despachos WHERE strftime("%Y", fecha_programada) = strftime("%Y", ?)', (fecha_programada,))
        despacho_numero = cursor.fetchone()[0] + 1
        codigo_despacho = f"DESP-{datetime.now().year}-{despacho_numero:04d}"

        # Insertar el despacho
        cursor.execute('''
            INSERT INTO despachos (
                proyecto_id, codigo_despacho, transportista, conductor, 
                telefono_conductor, vehiculo_patente, direccion_entrega, 
                fecha_programada, observaciones, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (proyecto_id, codigo_despacho, transportista, conductor, 
              telefono_conductor, vehiculo_patente, direccion_entrega, 
              fecha_programada, observaciones, 'programado'))

        despacho_id = cursor.lastrowid

        # Calcular fecha de recordatorio según la categoría del proyecto
        fecha_despacho = datetime.strptime(fecha_programada, '%Y-%m-%d').date()
        
        # Definir días de anticipación según el tipo de mueble/proyecto
        # Estas reglas se pueden ajustar según las necesidades del negocio
        recordatorio_dias = {
            'escritorio': 5,
            'comedor': 7,
            'cocina': 10,
            'dormitorio': 8,
            'oficina': 4,
            'living': 6,
            'default': 5
        }

        # Determinar categoría basada en el nombre del proyecto
        categoria_proyecto = 'default'
        nombre_proyecto_lower = proyecto[1].lower()
        for categoria in recordatorio_dias.keys():
            if categoria in nombre_proyecto_lower:
                categoria_proyecto = categoria
                break

        dias_anticipacion = recordatorio_dias[categoria_proyecto]
        fecha_recordatorio = fecha_despacho - timedelta(days=dias_anticipacion)

        # Crear recordatorio para el área de producción
        cursor.execute('SELECT id FROM areas WHERE nombre = "Producción" LIMIT 1')
        area_produccion = cursor.fetchone()
        area_id = area_produccion[0] if area_produccion else None

        titulo_recordatorio = f"Recordatorio: Finalizar producción para despacho {codigo_despacho}"
        mensaje_recordatorio = f"El proyecto '{proyecto[1]}' (código: {proyecto[2]}) debe estar listo para despacho el {fecha_programada}. Cliente: {proyecto[3]}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje, 
                fecha_recordatorio, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('despacho', despacho_id, area_id, titulo_recordatorio, 
              mensaje_recordatorio, fecha_recordatorio, True))

        # Crear recordatorio adicional para el día anterior al despacho
        fecha_recordatorio_urgente = fecha_despacho - timedelta(days=1)
        
        cursor.execute('SELECT id FROM areas WHERE nombre = "Despacho" LIMIT 1')
        area_despacho = cursor.fetchone()
        area_despacho_id = area_despacho[0] if area_despacho else None

        titulo_urgente = f"Despacho programado mañana: {codigo_despacho}"
        mensaje_urgente = f"Mañana ({fecha_programada}) está programado el despacho del proyecto '{proyecto[1]}' a {direccion_entrega}"

        cursor.execute('''
            INSERT INTO recordatorios (
                tipo, referencia_id, area_id, titulo, mensaje, 
                fecha_recordatorio, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('despacho', despacho_id, area_despacho_id, titulo_urgente, 
              mensaje_urgente, fecha_recordatorio_urgente, True))

        # Actualizar estado del proyecto si es necesario
        cursor.execute('UPDATE proyectos SET estado = "despacho" WHERE id = ? AND estado != "entregado"', (proyecto_id,))

        conn.commit()
        conn.close()

        flash(f'Despacho {codigo_despacho} programado exitosamente. Recordatorios creados automáticamente.', 'success')
        return redirect(url_for('proyecto_detalle', proyecto_id=proyecto_id))

    except Exception as e:
        flash(f'Error al programar despacho: {str(e)}', 'error')
        return redirect(request.referrer or url_for('proyectos'))


@app.route('/despachos')
@login_required
@role_required(['admin', 'general', 'despacho'])
def despachos():
    """Ver todos los despachos programados"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT d.*, p.nombre as proyecto_nombre, p.codigo as proyecto_codigo,
               c.nombre as cliente_nombre
        FROM despachos d
        JOIN proyectos p ON d.proyecto_id = p.id
        LEFT JOIN clientes c ON p.cliente_id = c.id
        ORDER BY d.fecha_programada ASC
    ''')
    despachos_list = cursor.fetchall()
    conn.close()
    
    return render_template('despachos.html', despachos=despachos_list)


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
