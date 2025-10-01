# Manufacturing Management System

## Overview

A comprehensive management system for manufacturing companies that centralizes the administration of clients, projects, contracts, manufacturing orders, and dispatches. The system provides complete tracking from initial client contact through project completion and delivery, with integrated document management, quality assurance workflows, and multi-role user access controls. Its purpose is to streamline operations, improve tracking, and enhance decision-making in a manufacturing environment. Key capabilities include financial payment status management, processing time tracking by area, strategic capacity planning, and project type customization with specific factors.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Technology Stack
- **Backend Framework**: Flask (Python) with SQLAlchemy ORM
- **Database**: PostgreSQL with Alembic migrations
- **Authentication**: Replit Auth integration with Flask-Login
- **File Storage**: Replit Object Storage
- **Data Validation**: Pydantic v2
- **Frontend**: Server-side rendered Jinja2 templates with responsive design

### Application Structure
The system follows a modular blueprint architecture with clear separation of concerns, utilizing blueprints for domain-specific modules, services for business logic, repositories for data access, and Pydantic models for data validation.

### Business Domain Architecture
- **Client Management**: Complete client master records with commercial information, contact tracking, and project history.
- **Project Lifecycle**: End-to-end project management from initial planning through completion, linked to clients, supporting multiple contracts, and state management across phases. Includes specific project types (Social, Estandar, Especial) with unique cost and time factors.
- **Contract & Purchase Order Management**: Handles contract/PO-based projects with document attachment, multi-currency support, payment terms, and delivery milestones.
- **Manufacturing Orders (OF)**: Production workflow management (planificada → en_producción → QA → terminada → entregada) with material tracking and quality control. Includes real-time vs. estimated time comparison for performance analysis.
- **Dispatch Management**: Logistics coordination (programado → en_transporte → entregado → observado) with delivery documentation and evidence collection.
- **Payment Status System**: Comprehensive financial management of payment statuses nested under projects, grouped by client, with invoicing functionality and specialized methods for financial analysis.
- **Processing Time Tracking**: Dynamic real-time tracking of processing time per area for manufacturing orders, providing historical data and statistics without schema modifications.
- **Strategic Capacity Planning**: Integral system for capacity planning (3-12 months horizon) based on operational parameters (machines, shifts, OEE) and hierarchical demand, including backlog logic, deficit scenarios, and gap analysis.

### Authentication & Authorization
- **Multi-role System**: Admin, Operations, Sales, Production, Logistics with granular permissions.
- **Dynamic Permission Management**: Granular permissions by role and module (Read, Create, Edit, Delete) with administrative interface and audit trail.
- **Session Management**: Persistent sessions with 31-day lifetime.

### Storage & File Management
- **Standardized Paths**: Organized storage structure (Client/Project hierarchy).
- **Multiple File Types**: Support for contracts, delivery documentation, and QA evidence.
- **Size Limits**: Configurable upload limits with MIME type validation.
- **Audit Trail**: Tracking of file operations.

### Database Design
- **Relational Structure**: Normalized schema with foreign key constraints.
- **Audit Fields**: Created/updated timestamps and user tracking.
- **State Management**: Enum-based status fields.

### UI/UX Decisions & Features
- **Responsive Design**: Server-side rendered Jinja2 templates.
- **Detailed Matrix Improvements**: Dropdowns for project details, next delivery milestone column, and order by days remaining.
- **Gantt Chart Enhancements**: Integration of contract milestones as vertical lines, and interactive dropdowns for Manufacturing Orders (OFs).
- **Print Optimization**: Configured for A4 horizontal and letter format, with automatic expansion of dropdowns and repeating column titles.
- **Visual Indicators**: Progress bars, status badges, and color-coded indicators for financial progress and time deviation analysis.

## External Dependencies

### Core Infrastructure
- **PostgreSQL Database**: Primary data store.
- **Replit Object Storage**: File storage service.
- **Replit Auth**: Authentication provider.

### Python Libraries
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-Dance.
- **Database**: psycopg2-binary.
- **Validation**: Pydantic v2.
- **Security**: Werkzeug.
- **Timezone**: pytz.
- **Image Processing**: Pillow.

### Development Tools
- **WSGI Server**: Gunicorn.
- **Proxy Handling**: ProxyFix.
- **Environment**: python-dotenv.
- **Logging**: Built-in Python logging.

### File Format Support
- **Documents**: PDF.
- **Images**: JPEG, PNG.

## Recent Changes

### 2025-10-01: Production Deployment and Health Check Improvements
- **Implemented comprehensive health check system** with three specialized endpoints for deployment monitoring
- **Key Features**:
  - `/health` endpoint with complete system diagnostics (database connectivity, environment variables, connection pool status)
  - `/health/live` liveness probe for basic application availability checks
  - `/health/ready` readiness probe verifying database schema and critical dependencies
  - All health checks return appropriate HTTP status codes (200 for healthy, 503 for unhealthy)
  - Sanitized error messages to prevent information disclosure while maintaining detailed server-side logging
- **Deployment Configuration**:
  - Updated to production-ready Gunicorn settings with 2 workers and 4 threads per worker
  - Configured timeout (120s) and graceful timeout (30s) for request handling
  - Enabled keep-alive connections and comprehensive access/error logging
- **Security Improvements**:
  - Error messages sanitized to avoid exposing sensitive system details
  - Detailed exceptions logged server-side for debugging while clients receive generic messages
- **Purpose**: Ensure robust deployment with proper health monitoring, enabling autoscaling platforms to accurately assess application state and readiness

### 2025-09-30: Archive System for Contracts and Dispatches
- **Implemented non-destructive archive system** for closed contracts and completed dispatches
- **Key Features**:
  - Archive/unarchive functionality for Contracts (CERRADO state only) and Dispatches (ENTREGADO state only)
  - Complete audit trail via AuditService for all archive operations
  - Filterable views: All, Active only, Archived only
  - Individual and bulk archive actions with confirmation dialogs
  - Role-based permissions (Admin/General for bulk operations)
- **Database Changes**: Added `archivado` boolean column with indexes to contratos and despachos tables
- **Technical Implementation**:
  - Repository layer validates state before archiving (business rules enforcement)
  - Service layer handles transactions and audit logging
  - Blueprint routes with appropriate role permissions
  - Templates with filter dropdowns and action buttons
- **Purpose**: Clean up main views by hiding closed/delivered items while maintaining full recoverability and audit compliance

### 2025-09-26: Expanded Productividad Real Analysis to Include Bodega Orders
- **Enhanced productivity analysis** to include orders in "Área Bodega" states (`listo_para_despacho`, `programado_para_despacho`)
- **Updated filtering logic** in ProductividadService to consider orders that completed manufacturing and packaging but haven't been dispatched yet
- **Improved statistical accuracy** by including orders that have finished production workflow but remain in warehouse
- **Purpose**: Provide more comprehensive productivity metrics by including all orders that have completed the manufacturing process, not just those with explicit completion dates

### 2025-09-09: Simplified Finance Module Implementation
- **Created simplified finance module** focused on project financial tracking
- **Key Features**:
  - Dashboard showing all projects with contracts and payment states
  - Payment state management (pending invoicing → invoiced → paid)
  - Support for typical payment types: advance/progress/retention
  - Manual cost entry from external ERP system
  - Financial analysis report with margins and collection status
- **Access Control**: Restricted to Admin and General roles
- **Purpose**: Provide lightweight financial tracking complementing existing ERP system

### 2025-09-09: Database Enum Synchronization
- **Synchronized all enum values across the codebase to match database values**:
  - Updated `EstadoOF` enum in models.py to use lowercase with underscores and Spanish characters (ñ)
  - Synchronized `EstadoPendientesFabricacion`, `EstadoFabrica`, `EstadoEmbalaje`, `EstadoBodega`, and `EstadoDespachoArea` enums
  - Updated schemas/fabricacion.py to use synchronized values
  - Updated constants/transitions.py to use lowercase values matching database
  - Fixed routes.py to use lowercase enum values
  - Added missing state `programado_para_despacho` to relevant enums
- **Purpose**: Ensure consistency between database values and code, preventing runtime errors from mismatched enum values
- **Impact**: All state comparisons now work correctly with database values

### 2025-09-10: Centro de Costo (CC) Field Addition
- **Added centro_costo field to Proyecto model**: Numeric field for ERP Mobikit integration
- **Updated Pydantic schemas**: Added centro_costo to ProyectoBase, ProyectoUpdate, and ProyectoResponse
- **Modified project forms**: Added Centro de Costo input field in creation and editing forms
- **Enhanced project detail view**: Centro de Costo displays in additional information section
- **Database schema updated**: New centro_costo column added to proyectos table
- **Purpose**: Enable linking projects between the app and ERP Mobikit system through numeric cost center codes

### 2025-09-10: Project Log/Journal (Bitácora) System Implementation
- **Created comprehensive project documentation system** for tracking technical specifications and project changes
- **Key Features**:
  - New "Bitácora" tab in project details with organized comment system
  - Categorized comments: Especificación, Cambio, Nota, General with color-coded badges
  - Real-time comment loading with filtering by type
  - Character counter (1000 max) with visual feedback
  - Delete functionality with confirmation dialog
  - Responsive modal interface for adding comments
- **Technical Implementation**:
  - BitacoraProyecto model with TipoBitacora enum for comment categorization
  - Complete Pydantic schemas for validation (BitacoraProyectoCreate, BitacoraProyectoFilters)
  - Dedicated service layer (bitacora_service) for business logic
  - RESTful API endpoints (/proyectos/{id}/bitacora) supporting GET, POST, DELETE operations
  - Client-side JavaScript for real-time UI updates and form handling
- **Database Structure**: New bitacora_proyecto table with foreign keys to proyectos and users
- **Purpose**: Enable documentation of technical specification changes, project modifications, and important notes throughout project lifecycle

### 2025-09-08: Database Redundancy Elimination
- **Removed redundant `usuarios` table**: Consolidated to use only the `users` table
- **Fixed cache cleaning and production data cleaning functions**: Added real-time logging and progress indicators
- **Standardized authentication**: All systems now use the unified `users` table