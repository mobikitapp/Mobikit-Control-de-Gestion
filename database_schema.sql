
-- PostgreSQL schema for Mobikit system

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables (be careful with this in production)
-- DROP TABLE IF EXISTS auditoria CASCADE;
-- DROP TABLE IF EXISTS recordatorios CASCADE;
-- DROP TABLE IF EXISTS evidencias CASCADE;
-- DROP TABLE IF EXISTS tareas CASCADE;
-- DROP TABLE IF EXISTS despacho_archivos CASCADE;
-- DROP TABLE IF EXISTS despachos CASCADE;
-- DROP TABLE IF EXISTS orden_fabricacion_categorias CASCADE;
-- DROP TABLE IF EXISTS ordenes_fabricacion CASCADE;
-- DROP TABLE IF EXISTS proyecto_categorias CASCADE;
-- DROP TABLE IF EXISTS entregas_contrato CASCADE;
-- DROP TABLE IF EXISTS proyectos CASCADE;
-- DROP TABLE IF EXISTS clientes CASCADE;
-- DROP TABLE IF EXISTS subcategorias_producto CASCADE;
-- DROP TABLE IF EXISTS categorias_producto CASCADE;
-- DROP TABLE IF EXISTS usuarios CASCADE;
-- DROP TABLE IF EXISTS areas CASCADE;
-- DROP TABLE IF EXISTS configuraciones CASCADE;

-- Areas table
CREATE TABLE IF NOT EXISTS areas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usuarios table
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'general', 'vendedor', 'operación', 'embalaje', 'despacho')),
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100),
    email VARCHAR(150) UNIQUE,
    telefono VARCHAR(20),
    area_id INTEGER REFERENCES areas(id),
    repl_user_id VARCHAR(100),
    activo BOOLEAN DEFAULT TRUE,
    ultimo_acceso TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Clientes table
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    rut VARCHAR(20) UNIQUE,
    email VARCHAR(150),
    telefono VARCHAR(20),
    direccion TEXT,
    ciudad VARCHAR(100),
    region VARCHAR(100),
    contacto_principal VARCHAR(200),
    observaciones TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categorias producto table
CREATE TABLE IF NOT EXISTS categorias_producto (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subcategorias producto table
CREATE TABLE IF NOT EXISTS subcategorias_producto (
    id SERIAL PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias_producto(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(categoria_id, nombre)
);

-- Proyectos table
CREATE TABLE IF NOT EXISTS proyectos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    nombre VARCHAR(200) NOT NULL,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    descripcion TEXT,
    adjudicacion_tipo VARCHAR(20) DEFAULT 'orden_compra' CHECK (adjudicacion_tipo IN ('contrato', 'orden_compra')),
    estado VARCHAR(30) DEFAULT 'diseño' CHECK (estado IN ('diseño', 'proyecto_simple', 'en_desarrollo', 'aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa', 'embalando', 'listo_despacho', 'entregado', 'terminado', 'completado', 'cancelado')),
    estado_proyecto VARCHAR(30) DEFAULT 'pendiente_presupuesto' CHECK (estado_proyecto IN ('pendiente_presupuesto', 'presupuestado', 'adjudicado')),
    prioridad VARCHAR(10) DEFAULT 'media' CHECK (prioridad IN ('alta', 'media', 'baja')),
    fecha_inicio DATE,
    fecha_entrega DATE,
    fecha_entrega_real DATE,
    fecha_estimada_inicio DATE,
    diseñador_id INTEGER REFERENCES usuarios(id),
    supervisor_id INTEGER REFERENCES usuarios(id),
    monto_neto DECIMAL(12,2),
    monto_neto_provision DECIMAL(12,2),
    monto_neto_instalacion DECIMAL(12,2),
    monto_provision_presupuestada DECIMAL(12,2),
    margen_provision DECIMAL(5,2),
    margen_instalacion DECIMAL(5,2),
    costo_real DECIMAL(12,2),
    observaciones TEXT,
    archivado BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ordenes de compra/contratos table
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    numero_orden VARCHAR(100) NOT NULL,
    tipo VARCHAR(20) DEFAULT 'orden_compra' CHECK (tipo IN ('orden_compra', 'contrato')),
    descripcion TEXT,
    monto_provision DECIMAL(12,2) NOT NULL,
    fecha_orden DATE,
    fecha_entrega_estimada DATE,
    estado VARCHAR(20) DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobada', 'en_proceso', 'completada', 'cancelada')),
    proveedor VARCHAR(200),
    observaciones TEXT,
    archivo_orden TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(proyecto_id, numero_orden)
);

-- Proyecto categorias table
CREATE TABLE IF NOT EXISTS proyecto_categorias (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categorias_producto(id),
    subcategoria_id INTEGER REFERENCES subcategorias_producto(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(proyecto_id, categoria_id, subcategoria_id)
);

-- Ordenes fabricacion table
CREATE TABLE IF NOT EXISTS ordenes_fabricacion (
    id SERIAL PRIMARY KEY,
    codigo_orden VARCHAR(50) UNIQUE NOT NULL,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id),
    tipo_orden VARCHAR(50) NOT NULL,
    estado VARCHAR(30) DEFAULT 'pendiente_aprobacion_diseño' CHECK (estado IN ('pendiente_aprobacion_diseño', 'aprobado_diseño', 'enviado_produccion', 'seccionado', 'enchapando', 'mecanizado', 'listo_embalaje', 'embalando', 'listo_despacho', 'despachado', 'entregado')),
    fecha_entrega_estimada DATE,
    fecha_inicio TIMESTAMP,
    fecha_entrega_real TIMESTAMP,
    cantidad_tableros INTEGER,
    glosa VARCHAR(200),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orden fabricacion categorias table
CREATE TABLE IF NOT EXISTS orden_fabricacion_categorias (
    id SERIAL PRIMARY KEY,
    orden_fabricacion_id INTEGER NOT NULL REFERENCES ordenes_fabricacion(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categorias_producto(id),
    subcategoria_id INTEGER REFERENCES subcategorias_producto(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Entregas contrato table
CREATE TABLE IF NOT EXISTS entregas_contrato (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    detalle TEXT NOT NULL,
    fecha_entrega DATE NOT NULL,
    estado VARCHAR(20) DEFAULT 'programada' CHECK (estado IN ('programada', 'en_preparacion', 'despachada', 'entregada')),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tareas table
CREATE TABLE IF NOT EXISTS tareas (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    estado VARCHAR(20) DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'en_progreso', 'completada', 'cancelada')),
    prioridad VARCHAR(10) DEFAULT 'media' CHECK (prioridad IN ('alta', 'media', 'baja')),
    tipo VARCHAR(30),
    fecha_programada DATE,
    fecha_inicio TIMESTAMP,
    fecha_completada TIMESTAMP,
    usuario_asignado_id INTEGER REFERENCES usuarios(id),
    rol_asignado VARCHAR(20),
    tiempo_estimado INTEGER,
    tiempo_real INTEGER,
    etapa_fabricacion VARCHAR(30) CHECK (etapa_fabricacion IN ('seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo')),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evidencias table
CREATE TABLE IF NOT EXISTS evidencias (
    id SERIAL PRIMARY KEY,
    tarea_id INTEGER REFERENCES tareas(id) ON DELETE CASCADE,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    nombre_archivo VARCHAR(255) NOT NULL,
    ruta_archivo VARCHAR(500) NOT NULL,
    descripcion TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Despachos table
CREATE TABLE IF NOT EXISTS despachos (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id),
    codigo_despacho VARCHAR(50) UNIQUE NOT NULL,
    transportista VARCHAR(200),
    conductor VARCHAR(200),
    telefono_conductor VARCHAR(20),
    vehiculo_patente VARCHAR(20),
    direccion_entrega TEXT NOT NULL,
    fecha_programada DATE NOT NULL,
    fecha_despacho TIMESTAMP,
    fecha_entrega TIMESTAMP,
    estado VARCHAR(20) DEFAULT 'programado' CHECK (estado IN ('programado', 'en_transito', 'entregado', 'cancelado')),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Despacho archivos table
CREATE TABLE IF NOT EXISTS despacho_archivos (
    id SERIAL PRIMARY KEY,
    despacho_id INTEGER NOT NULL REFERENCES despachos(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('foto', 'guia', 'checklist', 'firma', 'otro')),
    nombre_original VARCHAR(255) NOT NULL,
    ruta_archivo VARCHAR(500) NOT NULL,
    tamaño INTEGER,
    descripcion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recordatorios table
CREATE TABLE IF NOT EXISTS recordatorios (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('proyecto', 'despacho', 'tarea', 'general')),
    referencia_id INTEGER,
    usuario_id INTEGER REFERENCES usuarios(id),
    area_id INTEGER REFERENCES areas(id),
    titulo VARCHAR(200) NOT NULL,
    mensaje TEXT,
    fecha_recordatorio DATE NOT NULL,
    enviado BOOLEAN DEFAULT FALSE,
    fecha_envio TIMESTAMP,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auditoria table
CREATE TABLE IF NOT EXISTS auditoria (
    id SERIAL PRIMARY KEY,
    tabla_afectada VARCHAR(50) NOT NULL,
    registro_id INTEGER NOT NULL,
    accion VARCHAR(20) NOT NULL CHECK (accion IN ('INSERT', 'UPDATE', 'DELETE', 'ARCHIVE', 'UNARCHIVE')),
    usuario_id INTEGER REFERENCES usuarios(id),
    valores_anteriores JSONB,
    valores_nuevos JSONB,
    timestamp_accion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Configuraciones table
CREATE TABLE IF NOT EXISTS configuraciones (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    descripcion TEXT,
    tipo VARCHAR(20) DEFAULT 'string' CHECK (tipo IN ('string', 'integer', 'boolean', 'json')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documentos proyecto table
CREATE TABLE IF NOT EXISTS documentos_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    nombre_original VARCHAR(255) NOT NULL,
    ruta_archivo VARCHAR(500) NOT NULL,
    tipo_archivo VARCHAR(50) NOT NULL,
    tamaño INTEGER,
    descripcion TEXT,
    usuario_subida_id INTEGER REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default monthly objective configuration
INSERT INTO configuraciones (clave, valor, descripcion, tipo) VALUES
('objetivo_mensual_provision', '50000000', 'Objetivo mensual de ventas en provisión (pesos chilenos)', 'integer')
ON CONFLICT (clave) DO NOTHING;

-- Insert initial data
INSERT INTO areas (nombre, descripcion) VALUES
('Diseño', 'Área encargada del diseño y planificación de muebles'),
('Producción', 'Área de fabricación y manufactura'),
('Calidad', 'Control de calidad y supervisión'),
('Embalaje', 'Preparación y embalaje de productos'),
('Despacho', 'Logística y entrega de productos'),
('Administración', 'Gestión administrativa y financiera')
ON CONFLICT (nombre) DO NOTHING;

-- Insert sample categories
INSERT INTO categorias_producto (nombre, descripcion) VALUES
('Cocinas', 'Muebles de cocina modulares'),
('Closets', 'Sistemas de closet y vestidores'),
('Baños', 'Mobiliario para baños'),
('Oficina', 'Muebles de oficina'),
('Comercial', 'Mobiliario comercial')
ON CONFLICT (nombre) DO NOTHING;

-- Insert sample subcategories
INSERT INTO subcategorias_producto (categoria_id, nombre, descripcion) VALUES
((SELECT id FROM categorias_producto WHERE nombre = 'Cocinas'), 'Bases', 'Muebles base de cocina'),
((SELECT id FROM categorias_producto WHERE nombre = 'Cocinas'), 'Aéreos', 'Muebles aéreos de cocina'),
((SELECT id FROM categorias_producto WHERE nombre = 'Cocinas'), 'Torres', 'Torres y columnas de cocina'),
((SELECT id FROM categorias_producto WHERE nombre = 'Closets'), 'Puertas', 'Puertas de closet'),
((SELECT id FROM categorias_producto WHERE nombre = 'Closets'), 'Interiores', 'Accesorios interiores de closet')
ON CONFLICT (categoria_id, nombre) DO NOTHING;
