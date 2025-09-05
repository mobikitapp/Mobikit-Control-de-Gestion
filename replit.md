# Manufacturing Management System

## Overview

A comprehensive management system for manufacturing companies that centralizes administration of clients, projects, contracts, manufacturing orders, and dispatches. The system provides complete tracking from initial client contact through project completion and delivery, with integrated document management, quality assurance workflows, and multi-role user access controls.

## Recent Changes

**[2025-09-05] Sistema de Tipos de Proyectos con Factores Específicos - FINALIZADO**
- **TIPOS DE PROYECTO**: Implementación completa de enum TipoProyecto (Social/Estandar/Especial)
- **FACTORES POR TIPO**: Cada tipo tiene factores únicos de CLP/tablero y tiempos de fabricación/embalaje
  - SOCIAL: $180K/tablero, 0.040d fábrica, 0.015d embalaje
  - ESTANDAR: $210K/tablero, 0.030d fábrica, 0.012d embalaje (por defecto)
  - ESPECIAL: $280K/tablero, 0.025d fábrica, 0.010d embalaje
- **SIMPLIFICACIÓN MELAMINA**: Sistema enfocado únicamente en Melamina, eliminados MDF y Madera
- **NUEVA FÓRMULA**: Cálculo mejorado con margen: (Monto × (1-margen)) ÷ Factor_CLP_Tablero × Desperdicio
- **INTEGRACIÓN COMPLETA**: Todos los servicios actualizados para usar factores según tipo de proyecto
- **CONFIGURACIÓN DINÁMICA**: Factores de tiempo modificables por tipo de proyecto en interfaz web
- **FUNCIONALIDAD GUARDAR**: Sistema completo de actualización de factores con validación y logging
- Cálculos de capacidad mensual consideran tipo específico para estimaciones precisas
- Análisis de productividad incorpora diferencias por tipo de proyecto

**[2025-09-04] Comparación Tiempo Real vs Estimado - Análisis de Rendimiento**
- **CÁLCULO TIEMPO REAL**: Automatización de tiempo real de fabricación (fecha planificada → fecha fab)  
- **TIEMPO REAL EMBALAJE**: Cálculo automático de tiempo real de embalaje (fecha fab → fecha embalaje)
- **COMPARACIÓN VISUAL**: Indicadores de desviación tiempo real vs estimado con porcentajes
- **BADGES INTELIGENTES**: Sistema de colores por nivel de desviación (>50% rojo, >20% amarillo, >20% antes verde)
- **LEYENDA ACTUALIZADA**: Explicación completa de indicadores de desviación temporal
- Datos para ajuste de factores de cálculo de estimaciones de tiempo
- Análisis de rendimiento para mejorar precisión de planificación futura

**[2025-09-04] Mejoras en Matriz Detallada - Nueva Funcionalidad de Dropdowns y Ordenación**
- **DROPDOWNS DE PROYECTOS**: Implementación de lista desplegable para detalles de cada proyecto
- **HITOS DE ENTREGA**: Nueva columna de próximo hito de entrega con días restantes
- **ORDENACIÓN POR DÍAS**: Proyectos ordenados por días restantes según sus OFs (menor a mayor)
- **ELIMINACIÓN CRONOGRAMA VISUAL**: Removido campo cronograma visual para optimizar espacio
- **TIEMPO ESTIMADO REORGANIZADO**: Tiempo estimado ahora aparece debajo de fechas de fabricación y embalaje
- Funcionalidad colapsable con iconos + / - para cada proyecto
- Impresión mejorada que abre automáticamente todos los dropdowns
- JavaScript actualizado para manejar eventos de apertura/cierre de dropdowns
- Cálculo inteligente de días restantes usando mínimo entre OFs y hitos de entrega

**[2025-09-04] Mejoras en Planificación y Prioridades - Actualización de Impresión**
- **FORMATO CARTA**: Configuración de impresión cambiada de A4 horizontal a formato carta (8.5"x11")
- **DROPDOWNS ABIERTOS**: Implementación automática de apertura de todos los dropdowns de OFs al imprimir
- **TÍTULOS REPETIDOS**: Configuración CSS para repetir títulos de columnas en cada cambio de página
- **ESTILOS DE IMPRESIÓN**: Optimización de estilos para dropdowns y elementos de tabla en impresión
- JavaScript mejorado que gestiona estado de dropdowns antes y después de imprimir
- CSS específico para display: table-header-group que asegura repetición de thead

**[2025-09-04] Mejoras en Planificación y Prioridades - Primera Implementación**
- Corregida la fila de totales en Gantt de proyectos para coincidir con el cronograma unificado de 6 semanas
- Implementada funcionalidad completa de impresión con botones separados para Gantt y matriz detallada
- Agregados estilos CSS optimizados para impresión en formato A4 horizontal
- Implementadas funciones JavaScript que ocultan automáticamente secciones irrelevantes al imprimir
- Corregida ruta del blueprint de planificación operacional a `/prioridades`
- Eliminado código duplicado que causaba errores de startup del servidor
- **NUEVOS HITOS DE ENTREGA**: Integración completa de hitos de contratos en Gantt de proyectos
- Líneas verticales amarillas que muestran fechas de hitos de entrega en cronograma de 6 semanas
- Nueva columna "Días Restantes" que muestra días hasta próximo hito de entrega por proyecto
- Método `get_hitos_entrega_proyecto()` para obtener hitos de entrega de contratos asociados
- Cálculo automático de posicionamiento de hitos dentro del rango temporal de 6 semanas
- Tooltips informativos en líneas de hitos con título, fecha y días restantes
- Leyenda actualizada incluyendo explicación de líneas amarillas de hitos
- **LISTA DESPLEGABLE DE OFs**: Reemplazo de contador simple por dropdown interactivo
- Dropdown de Órdenes de Fabricación muestra código, prioridad y fechas de cada OF
- Vista detallada con código completo, prioridad numérica/textual y fechas codificadas por colores
- Información de tableros por OF y separadores visuales entre elementos
- Centrado mejorado de títulos de columnas "Total" y "Días Próximo Hito"

**[2025-09-03] Sistema de Gestión de Permisos Dinámicos**
- Implementado sistema completo de gestión de permisos por rol y módulo 
- Interfaz administrativa para configurar permisos granulares (Lectura, Creación, Edición, Eliminación)
- Sistema de auditoría completo que registra todos los cambios de permisos
- Inicialización automática de 9 módulos del sistema con 216 combinaciones de permisos
- Integración con sistema de permisos estático existente como fallback
- Nuevas tablas: modulos, permisos_rol, auditoria_permisos
- Nuevas rutas: /configuraciones/permisos/gestionar, /configuraciones/permisos/auditoria

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Technology Stack
- **Backend Framework**: Flask (Python) with SQLAlchemy ORM for database operations
- **Database**: PostgreSQL with Alembic migrations via Flask-Migrate
- **Authentication**: Replit Auth integration with Flask-Login for session management
- **File Storage**: Replit Object Storage for document and media files
- **Data Validation**: Pydantic v2 for request/response validation
- **Frontend**: Server-side rendered Jinja2 templates with responsive design

### Application Structure
The system follows a modular blueprint architecture with clear separation of concerns:

- **Blueprints**: Domain-specific modules (clientes, proyectos, contratos, fabricacion, despachos)
- **Services**: Business logic layer handling complex operations and workflows
- **Repositories**: Data access layer abstracting database operations
- **Models**: SQLAlchemy entity definitions with enum-based status management
- **Schemas**: Pydantic models for data validation and serialization
- **Adapters**: External service integrations (storage, notifications)

### Business Domain Architecture

**Client Management**: Complete client master records with commercial information, contact tracking, and project history. Supports both individual and corporate clients with configurable commercial terms.

**Project Lifecycle**: End-to-end project management from initial planning through completion. Projects are linked to clients and can have multiple contracts/purchase orders. State management covers planning, development, production phases, and final delivery.

**Contract & Purchase Order Management**: Handles both contract-based and purchase order-based projects with flexible document attachment system. Supports multiple currencies, payment terms, and delivery milestones with comprehensive audit trails.

**Manufacturing Orders (OF)**: Production workflow management with states: planificada → en_producción → QA → terminada → entregada. Includes material tracking, responsible party assignment, and quality control checkpoints.

**Dispatch Management**: Logistics coordination with states: programado → en_transporte → entregado → observado. Integrates delivery documentation (guides, delivery receipts) and evidence collection (photos, signatures).

### Authentication & Authorization
- **Multi-role System**: Admin, Operations, Sales, Production, Logistics with granular permissions
- **Session Management**: Persistent sessions with 31-day lifetime
- **Access Control**: Role-based access to features and data with audit logging

### Storage & File Management
- **Standardized Paths**: Organized storage structure following Cliente/Proyecto hierarchy:
  - `Cliente-{id}/Proyecto-{id}/Contratos/{contrato_id}/{docs|evidencias}/`
  - `Cliente-{id}/Proyecto-{id}/Despachos/{despacho_id}/{docs|evidencias}/`
- **Multiple File Types**: Support for contracts, delivery documentation, and QA evidence
- **Size Limits**: Configurable upload limits (default 25MB) with MIME type validation
- **Audit Trail**: Complete tracking of file uploads, downloads, and modifications
- **Backward Compatibility**: Legacy structure still supported for existing files

### Database Design
- **Relational Structure**: Normalized schema with proper foreign key constraints
- **Audit Fields**: Created/updated timestamps and user tracking on all entities
- **State Management**: Enum-based status fields with database constraints
- **Indexing**: Strategic indexes on frequently queried fields (client search, project filtering)
- **Transactions**: ACID compliance for critical business operations

### Search & Filtering
- **Full-text Search**: Cross-entity search capabilities for clients, projects, and documents
- **Advanced Filtering**: Date ranges, status filters, responsible party filters
- **Pagination**: Efficient pagination for large datasets
- **Export Capabilities**: Data export functionality for reporting and analysis

## External Dependencies

### Core Infrastructure
- **PostgreSQL Database**: Primary data store with ACID transactions and full-text search
- **Replit Object Storage**: File storage service for documents, images, and attachments
- **Replit Auth**: Authentication provider with OAuth2 integration

### Python Libraries
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-Dance
- **Database**: psycopg2-binary for PostgreSQL connectivity
- **Validation**: Pydantic v2 for data validation and serialization
- **Security**: Werkzeug for secure filename handling and password utilities
- **Timezone**: pytz for Santiago/Chile timezone management
- **Image Processing**: Pillow for image handling and optimization

### Development Tools
- **WSGI Server**: Gunicorn for production deployment
- **Proxy Handling**: ProxyFix middleware for proper HTTPS URL generation
- **Environment**: python-dotenv for configuration management
- **Logging**: Built-in Python logging with configurable levels

### File Format Support
- **Documents**: PDF files for contracts and official documents
- **Images**: JPEG, PNG for photos and visual evidence
- **MIME Validation**: Configurable allowed file types with server-side validation