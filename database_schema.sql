
-- Esquema completo de base de datos para Mobikit
-- Compatible con SQLite y optimizado para Replit

-- Tabla de áreas/departamentos
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    responsable_id INTEGER,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (responsable_id) REFERENCES usuarios (id)
);

-- Tabla de usuarios (expandida)
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('admin', 'general', 'diseñador', 'operación', 'embalaje', 'despacho')),
    nombre TEXT NOT NULL,
    apellido TEXT,
    email TEXT UNIQUE,
    telefono TEXT,
    area_id INTEGER,
    activo BOOLEAN DEFAULT TRUE,
    ultimo_acceso TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (area_id) REFERENCES areas (id)
);

-- Tabla de clientes (nueva)
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
);

-- Tabla de proyectos/obras (expandida)
CREATE TABLE IF NOT EXISTS proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL, -- Código único del proyecto
    nombre TEXT NOT NULL,
    cliente_id INTEGER NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'diseño' CHECK (estado IN ('diseño', 'aprobado', 'producción', 'embalaje', 'despacho', 'entregado', 'cancelado')),
    prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
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
);

-- Tabla de tareas (expandida)
CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    codigo TEXT, -- Código de tarea opcional
    titulo TEXT NOT NULL,
    descripcion TEXT,
    tipo TEXT DEFAULT 'general' CHECK (tipo IN ('diseño', 'fabricación', 'control_calidad', 'embalaje', 'despacho', 'general')),
    rol_asignado TEXT NOT NULL,
    usuario_asignado_id INTEGER,
    area_id INTEGER,
    estado TEXT DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'en_progreso', 'pausada', 'completada', 'cancelada')),
    prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
    fecha_programada DATE,
    fecha_inicio TIMESTAMP,
    fecha_completada TIMESTAMP,
    tiempo_estimado INTEGER, -- En horas
    tiempo_real INTEGER, -- En horas
    etapa_fabricacion TEXT CHECK (etapa_fabricacion IN ('seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo')), -- Etapas específicas de operación
    dependencias TEXT, -- JSON con IDs de tareas dependientes
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
    FOREIGN KEY (usuario_asignado_id) REFERENCES usuarios (id),
    FOREIGN KEY (area_id) REFERENCES areas (id)
);

-- Tabla de evidencias (expandida)
CREATE TABLE IF NOT EXISTS evidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarea_id INTEGER,
    proyecto_id INTEGER, -- Evidencias pueden estar asociadas directamente al proyecto
    tipo TEXT NOT NULL CHECK (tipo IN ('foto', 'documento', 'video', 'audio', 'otro')),
    archivo TEXT NOT NULL,
    nombre_original TEXT,
    tamaño INTEGER, -- En bytes
    descripcion TEXT,
    etiquetas TEXT, -- JSON con etiquetas/tags
    usuario_id INTEGER NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tarea_id) REFERENCES tareas (id),
    FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

-- Tabla de despachos (nueva)
CREATE TABLE IF NOT EXISTS despachos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER, -- Ahora opcional para permitir entrada manual
    codigo_despacho TEXT UNIQUE NOT NULL,
    transportista TEXT,
    conductor TEXT,
    telefono_conductor TEXT,
    vehiculo_patente TEXT,
    direccion_entrega TEXT NOT NULL,
    fecha_programada DATE,
    fecha_real DATE,
    hora_salida TIME,
    hora_llegada TIME,
    estado TEXT DEFAULT 'programado' CHECK (estado IN ('programado', 'en_transito', 'entregado', 'reprogramado', 'cancelado')),
    observaciones TEXT,
    recibido_por TEXT,
    firma_recepcion TEXT, -- Path a imagen de firma
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proyecto_id) REFERENCES proyectos (id)
);

-- Tabla de archivos de despacho
CREATE TABLE IF NOT EXISTS despacho_archivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    despacho_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('foto', 'guia', 'checklist', 'firma', 'otro')),
    nombre_original TEXT NOT NULL,
    ruta_archivo TEXT NOT NULL,
    tamaño INTEGER, -- En bytes
    descripcion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (despacho_id) REFERENCES despachos (id)
);

-- Tabla de recordatorios (expandida)
CREATE TABLE IF NOT EXISTS recordatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('tarea', 'proyecto', 'despacho', 'general')),
    referencia_id INTEGER, -- ID de la entidad relacionada
    usuario_id INTEGER,
    area_id INTEGER,
    titulo TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    fecha_recordatorio TIMESTAMP NOT NULL,
    repetir BOOLEAN DEFAULT FALSE,
    intervalo_repeticion TEXT, -- 'diario', 'semanal', 'mensual'
    activo BOOLEAN DEFAULT TRUE,
    enviado BOOLEAN DEFAULT FALSE,
    fecha_envio TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
    FOREIGN KEY (area_id) REFERENCES areas (id)
);

-- Tabla de incidencias (nueva)
CREATE TABLE IF NOT EXISTS incidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER,
    tarea_id INTEGER,
    usuario_reporta_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('calidad', 'retraso', 'material', 'equipo', 'seguridad', 'otro')),
    severidad TEXT DEFAULT 'media' CHECK (severidad IN ('baja', 'media', 'alta', 'crítica')),
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    estado TEXT DEFAULT 'abierta' CHECK (estado IN ('abierta', 'en_revision', 'en_proceso', 'resuelta', 'cerrada')),
    usuario_asignado_id INTEGER,
    fecha_resolucion TIMESTAMP,
    solucion TEXT,
    costo_incidencia DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
    FOREIGN KEY (tarea_id) REFERENCES tareas (id),
    FOREIGN KEY (usuario_reporta_id) REFERENCES usuarios (id),
    FOREIGN KEY (usuario_asignado_id) REFERENCES usuarios (id)
);

-- Tabla de notificaciones (nueva)
CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('info', 'warning', 'error', 'success')),
    titulo TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    leida BOOLEAN DEFAULT FALSE,
    url_accion TEXT, -- URL para redirigir al hacer clic
    metadatos TEXT, -- JSON con datos adicionales
    expira_en TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

-- Tabla de auditoría (nueva)
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla_afectada TEXT NOT NULL,
    registro_id INTEGER NOT NULL,
    accion TEXT NOT NULL CHECK (accion IN ('INSERT', 'UPDATE', 'DELETE')),
    usuario_id INTEGER,
    valores_anteriores TEXT, -- JSON con valores antes del cambio
    valores_nuevos TEXT, -- JSON con valores después del cambio
    ip_address TEXT,
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

-- Tabla de configuraciones del sistema (nueva)
CREATE TABLE IF NOT EXISTS configuraciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT UNIQUE NOT NULL,
    valor TEXT,
    descripcion TEXT,
    tipo TEXT DEFAULT 'string' CHECK (tipo IN ('string', 'integer', 'boolean', 'json')),
    updated_by INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (updated_by) REFERENCES usuarios (id)
);

-- Tabla de archivos/documentos del proyecto (nueva)
CREATE TABLE IF NOT EXISTS documentos_proyecto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    tipo_documento TEXT CHECK (tipo_documento IN ('plano', 'especificacion', 'contrato', 'presupuesto', 'otro')),
    archivo TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    descripcion TEXT,
    usuario_subida_id INTEGER NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
    FOREIGN KEY (usuario_subida_id) REFERENCES usuarios (id)
);

-- Índices para optimizar consultas
CREATE INDEX IF NOT EXISTS idx_proyectos_cliente ON proyectos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_proyectos_estado ON proyectos(estado);
CREATE INDEX IF NOT EXISTS idx_proyectos_fecha_entrega ON proyectos(fecha_entrega);
CREATE INDEX IF NOT EXISTS idx_tareas_proyecto ON tareas(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_tareas_usuario ON tareas(usuario_asignado_id);
CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas(estado);
CREATE INDEX IF NOT EXISTS idx_tareas_fecha ON tareas(fecha_programada);
CREATE INDEX IF NOT EXISTS idx_evidencias_tarea ON evidencias(tarea_id);
CREATE INDEX IF NOT EXISTS idx_evidencias_proyecto ON evidencias(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_recordatorios_usuario ON recordatorios(usuario_id);
CREATE INDEX IF NOT EXISTS idx_recordatorios_fecha ON recordatorios(fecha_recordatorio);
CREATE INDEX IF NOT EXISTS idx_incidencias_proyecto ON incidencias(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_incidencias_estado ON incidencias(estado);
CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario ON notificaciones(usuario_id);
CREATE INDEX IF NOT EXISTS idx_notificaciones_leida ON notificaciones(leida);
CREATE INDEX IF NOT EXISTS idx_auditoria_tabla_registro ON auditoria(tabla_afectada, registro_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(usuario_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_timestamp ON auditoria(timestamp);

-- Triggers para actualizar automáticamente updated_at
CREATE TRIGGER IF NOT EXISTS update_usuarios_timestamp 
    AFTER UPDATE ON usuarios
    BEGIN
        UPDATE usuarios SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_proyectos_timestamp 
    AFTER UPDATE ON proyectos
    BEGIN
        UPDATE proyectos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_tareas_timestamp 
    AFTER UPDATE ON tareas
    BEGIN
        UPDATE tareas SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_despachos_timestamp 
    AFTER UPDATE ON despachos
    BEGIN
        UPDATE despachos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_incidencias_timestamp 
    AFTER UPDATE ON incidencias
    BEGIN
        UPDATE incidencias SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

-- Triggers de auditoría para tracking de cambios
CREATE TRIGGER IF NOT EXISTS audit_usuarios_insert
    AFTER INSERT ON usuarios
    BEGIN
        INSERT INTO auditoria (tabla_afectada, registro_id, accion, valores_nuevos)
        VALUES ('usuarios', NEW.id, 'INSERT', 
                json_object('username', NEW.username, 'nombre', NEW.nombre, 'rol', NEW.rol));
    END;

CREATE TRIGGER IF NOT EXISTS audit_proyectos_insert
    AFTER INSERT ON proyectos
    BEGIN
        INSERT INTO auditoria (tabla_afectada, registro_id, accion, valores_nuevos)
        VALUES ('proyectos', NEW.id, 'INSERT', 
                json_object('codigo', NEW.codigo, 'nombre', NEW.nombre, 'estado', NEW.estado));
    END;

CREATE TRIGGER IF NOT EXISTS audit_tareas_update
    AFTER UPDATE ON tareas
    BEGIN
        INSERT INTO auditoria (tabla_afectada, registro_id, accion, valores_anteriores, valores_nuevos)
        VALUES ('tareas', NEW.id, 'UPDATE', 
                json_object('estado', OLD.estado, 'usuario_asignado_id', OLD.usuario_asignado_id),
                json_object('estado', NEW.estado, 'usuario_asignado_id', NEW.usuario_asignado_id));
    END;

-- Datos iniciales
INSERT OR IGNORE INTO areas (nombre, descripcion) VALUES 
    ('Diseño', 'Área encargada del diseño y planificación de muebles'),
    ('Producción', 'Área de fabricación y manufactura'),
    ('Calidad', 'Control de calidad y supervisión'),
    ('Embalaje', 'Preparación y embalaje de productos'),
    ('Despacho', 'Logística y entrega de productos'),
    ('Administración', 'Gestión administrativa y financiera');

INSERT OR IGNORE INTO configuraciones (clave, valor, descripcion, tipo) VALUES 
    ('empresa_nombre', 'Mobikit', 'Nombre de la empresa', 'string'),
    ('empresa_rut', '12345678-9', 'RUT de la empresa', 'string'),
    ('notificaciones_email', 'true', 'Activar notificaciones por email', 'boolean'),
    ('tiempo_sesion_minutos', '480', 'Duración de sesión en minutos', 'integer'),
    ('backup_automatico', 'true', 'Realizar backup automático diario', 'boolean');
