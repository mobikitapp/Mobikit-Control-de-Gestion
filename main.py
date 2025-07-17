
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
        cursor.execute('''
            INSERT INTO usuarios (username, password_hash, rol, nombre, email, activo)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('admin', admin_password, 'admin', 'Administrador', 'admin@mobikit.com', True))
    
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
        cursor.execute('SELECT id, password_hash, rol, nombre FROM usuarios WHERE username = ?', (username,))
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
    cursor.execute('''
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
        SELECT id, nombre, cliente, estado, fecha_entrega
        FROM proyectos
        ORDER BY created_at DESC
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
        SELECT p.id, p.nombre, p.cliente, p.estado, p.fecha_entrega, u.nombre as diseñador
        FROM proyectos p
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
    cursor.execute('''
        SELECT p.*, u.nombre as diseñador
        FROM proyectos p
        LEFT JOIN usuarios u ON p.diseñador_id = u.id
        WHERE p.id = ?
    ''', (proyecto_id,))
    proyecto = cursor.fetchone()
    
    # Tareas del proyecto
    cursor.execute('''
        SELECT t.*, u.nombre as asignado
        FROM tareas t
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.proyecto_id = ?
        ORDER BY t.fecha_programada ASC
    ''', (proyecto_id,))
    tareas = cursor.fetchall()
    
    conn.close()
    
    if not proyecto:
        flash('Proyecto no encontrado', 'error')
        return redirect(url_for('proyectos'))
    
    return render_template('proyecto_detalle.html', proyecto=proyecto, tareas=tareas)

@app.route('/nuevo_proyecto', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'general', 'diseñador'])
def nuevo_proyecto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        cliente = request.form['cliente']
        descripcion = request.form['descripcion']
        fecha_entrega = request.form['fecha_entrega']
        
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO proyectos (nombre, cliente, descripcion, fecha_entrega, diseñador_id, fecha_inicio)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nombre, cliente, descripcion, fecha_entrega, session['user_id'], datetime.now().date()))
        
        proyecto_id = cursor.lastrowid
        
        # Crear tareas automáticas del ciclo de vida
        tareas_ciclo = [
            ('Diseño inicial', 'Crear diseño y planos del mueble', 'diseñador', 1),
            ('Revisión de diseño', 'Revisar y aprobar diseño', 'general', 3),
            ('Planificación de producción', 'Planificar proceso de fabricación', 'operación', 5),
            ('Fabricación', 'Fabricar el mueble según especificaciones', 'operación', 15),
            ('Control de calidad', 'Revisar calidad del producto terminado', 'operación', 18),
            ('Embalaje', 'Embalar producto para despacho', 'embalaje', 20),
            ('Preparación de despacho', 'Preparar documentos y coordinar entrega', 'despacho', 22),
            ('Entrega', 'Entregar producto al cliente', 'despacho', 24)
        ]
        
        fecha_base = datetime.now().date()
        for titulo, descripcion, rol, dias in tareas_ciclo:
            fecha_programada = fecha_base + timedelta(days=dias)
            cursor.execute('''
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
        cursor.execute('''
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
    
    cursor.execute('''
        SELECT t.*, p.nombre as proyecto, u.nombre as asignado
        FROM tareas t
        JOIN proyectos p ON t.proyecto_id = p.id
        LEFT JOIN usuarios u ON t.usuario_asignado_id = u.id
        WHERE t.id = ?
    ''', (tarea_id,))
    tarea = cursor.fetchone()
    
    cursor.execute('''
        SELECT * FROM evidencias WHERE tarea_id = ? ORDER BY uploaded_at DESC
    ''', (tarea_id,))
    evidencias = cursor.fetchall()
    
    conn.close()
    
    if not tarea:
        flash('Tarea no encontrada', 'error')
        return redirect(url_for('tareas'))
    
    return render_template('tarea_detalle.html', tarea=tarea, evidencias=evidencias)

@app.route('/completar_tarea/<int:tarea_id>', methods=['POST'])
@login_required
def completar_tarea(tarea_id):
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    # Verificar que el usuario puede completar esta tarea
    cursor.execute('''
        SELECT rol_asignado, usuario_asignado_id FROM tareas WHERE id = ?
    ''', (tarea_id,))
    tarea = cursor.fetchone()
    
    if not tarea:
        flash('Tarea no encontrada', 'error')
        return redirect(url_for('tareas'))
    
    if (tarea[0] != session['user_role'] and 
        tarea[1] != session['user_id'] and 
        session['user_role'] != 'admin'):
        flash('No tienes permisos para completar esta tarea', 'error')
        return redirect(url_for('tarea_detalle', tarea_id=tarea_id))
    
    cursor.execute('''
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
    cursor.execute('SELECT id, username, nombre, rol, email, created_at FROM usuarios ORDER BY created_at DESC')
    usuarios_list = cursor.fetchall()
    conn.close()
    
    return render_template('usuarios.html', usuarios=usuarios_list, roles=ROLES)

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
        cursor.execute('''
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
