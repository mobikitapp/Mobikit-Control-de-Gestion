# Sistema de Manufactura

Sistema integral de gestión para empresas manufactureras que permite administrar clientes, proyectos, contratos, órdenes de fabricación y despachos de manera centralizada.

## 🚀 Características

### Gestión de Clientes
- Registro completo de clientes con información comercial
- Seguimiento de contactos y condiciones comerciales
- Historial de proyectos y contratos

### Proyectos
- Administración de proyectos por cliente
- Control de estados y fechas
- Asignación de responsables
- Seguimiento de progreso

### Contratos y Órdenes de Compra
- Gestión de contratos vinculados a proyectos
- Control de montos, fechas y condiciones
- Manejo de estados (borrador, vigente, cerrado, anulado)
- Sistema de adjuntos para documentos

### Órdenes de Fabricación
- Creación y seguimiento de órdenes de fabricación
- Workflow completo: planificada → en_producción → QA → terminada → entregada
- Gestión de items y materiales
- Control de fechas y responsables

### Despachos
- Programación y seguimiento de despachos
- Estados: programado → en_transporte → entregado → observado
- Gestión de destinos y contactos
- Documentación y evidencias (guías, actas, fotos)

### Características Técnicas
- **Autenticación:** Integración con Replit Auth
- **Roles de Usuario:** Admin, Operaciones, Ventas, Producción, Logística
- **Auditoría:** Registro completo de cambios
- **Storage:** Integración con Replit Storage para archivos
- **Responsive:** Interface adaptable a móviles y tablets

## 🛠️ Stack Tecnológico

### Backend
- **Framework:** Flask (Python)
- **Base de Datos:** PostgreSQL
- **ORM:** SQLAlchemy
- **Migraciones:** Alembic (Flask-Migrate)
- **Validación:** Pydantic v2
- **Autenticación:** Replit Auth (OAuth2/OIDC)

### Frontend
- **Framework CSS:** Bootstrap 5 (tema oscuro de Replit)
- **Icons:** Feather Icons
- **JavaScript:** Vanilla JS con componentes modulares
- **Forms:** HTML5 con validación client/server

### Infraestructura
- **Hosting:** Replit
- **Storage:** Replit Storage
- **Session Storage:** PostgreSQL (via SQLAlchemy)

## 📋 Requisitos Previos

- Python 3.9+
- PostgreSQL 12+
- Cuenta en Replit (para autenticación y storage)

## 🚀 Instalación y Configuración

### 1. Variables de Entorno

Copia el archivo `.env.example` a `.env` y configura las variables:

```bash
cp .env.example .env
