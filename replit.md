# Manufacturing Management System

## Overview
A comprehensive management system designed for manufacturing companies to centralize the administration of clients, projects, contracts, manufacturing orders, and dispatches. The system's core purpose is to streamline operations, improve tracking, and enhance decision-making by providing end-to-end visibility from initial client contact through project completion and delivery. Key capabilities include integrated document management, quality assurance workflows, multi-role user access controls, financial payment status management, processing time tracking by area, strategic capacity planning, and customizable project types with specific factors.

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
The system utilizes a modular blueprint architecture, separating concerns into domain-specific modules, services for business logic, repositories for data access, and Pydantic models for data validation.

### Business Domain Architecture
- **Client Management**: Manages client records, contacts, and project history.
- **Project Lifecycle**: Supports end-to-end project management, including multiple contracts and state management across phases, with specific project types (Social, Estandar, Especial) impacting cost and time. Includes a project log/journal system for tracking technical specifications and changes with categorized comments.
- **Contract & Purchase Order Management**: Handles contract/PO-based projects with document attachment, multi-currency support, payment terms, and delivery milestones. Features a non-destructive archive system for closed contracts.
- **Manufacturing Orders (OF)**: Manages production workflows (planned → in_production → QA → finished → delivered) with material tracking, quality control, and real-time vs. estimated time comparison.
- **Dispatch Management**: Coordinates logistics (scheduled → in_transit → delivered → observed) with documentation and evidence collection. Features a non-destructive archive system for completed dispatches.
- **Payment Status System**: Manages financial payment statuses nested under projects, grouped by client, with invoicing functionality and financial analysis. Includes a simplified finance module for project financial tracking.
- **Processing Time Tracking**: Dynamically tracks processing time per area for manufacturing orders, providing historical data.
- **Strategic Capacity Planning**: Provides a system for capacity planning (3-12 months horizon) based on operational parameters and hierarchical demand, including backlog and gap analysis.
- **Productivity Analysis**: Enhanced to include orders in "Área Bodega" states for comprehensive metrics.

### Authentication & Authorization
- **Multi-role System**: Supports Admin, Operations, Sales, Production, Logistics roles with granular permissions.
- **Dynamic Permission Management**: Granular permissions by role and module (Read, Create, Edit, Delete) with an administrative interface.
- **Secure Registration**: New users register without an assigned role and require administrator approval.

### Storage & File Management
- **Standardized Paths**: Organizes files hierarchically (Client/Project).
- **Multiple File Types**: Supports contracts, delivery documentation, and QA evidence.
- **Size Limits**: Configurable upload limits with MIME type validation.

### Database Design
- **Relational Structure**: Normalized schema with foreign key constraints.
- **Audit Fields**: Includes created/updated timestamps and user tracking.
- **State Management**: Uses enum-based status fields, with synchronized enum values across the codebase.
- **Project Enhancements**: Includes a `centro_costo` field for ERP integration and a `bitacora_proyecto` table for project logs.

### UI/UX Decisions & Features
- **Responsive Design**: Server-side rendered Jinja2 templates.
- **Visual Indicators**: Utilizes progress bars, status badges, and color-coded indicators for financial progress and time deviation.
- **Gantt Chart Enhancements**: Integrates contract milestones and interactive dropdowns for Manufacturing Orders.
- **Print Optimization**: Configured for A4 horizontal and letter format.
- **Notification System**: Separated user notifications from admin configuration with user-specific views and admin-only preferences.

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

### File Format Support
- **Documents**: PDF.
- **Images**: JPEG, PNG.

## Recent Changes
- **2025-10-02 (afternoon)**: **Comprehensive update to training module (capacitación)** - Completely revised the training content to accurately reflect real application functionalities without mentioning permissions or inventing non-existent features. Key changes:
  * **Áreas de Producción**: Corrected production flow with 5 real areas (Pendiente Fabricación, Fabrica, Embalaje, Bodega, Despacho) and 13 Manufacturing Order states properly documented. Added dashboard, history, and intelligent advancement features.
  * **Comercial**: Completely rewritten with real features: vendor list with statistics, commercial project management, tasks, monthly planning matrix, objectives and commissions.
  * **Calendario**: NEW module added with monthly/weekly/daily views, delivery milestones, and strategic analysis integration.
  * **Configuraciones**: Updated with real admin features: user management, dynamic permission system, audit trail, system configuration, notification preferences.
  * **Clientes & Flujo General**: Removed invented distinction between "Persona Natural" and "Empresa" - unified generic client model correctly reflected.
  * **Mi Dashboard**: NEW module added - personal vendor dashboard with metrics, success rate, active projects, recent clients, pending tasks, and average margins.
  * **Permissions cleanup**: Removed all mentions of permissions/roles outside the Configuraciones module per user requirements.
  * Training content now focuses exclusively on WHAT each module does, not who can access it. All documented features verified against actual codebase.
- **2025-10-02 (morning)**: **Fixed commercial status change logic in project edit form** - Modified `_aplicar_cambios_automaticos_estado()` to respect manual status changes by users. The system now captures the commercial status BEFORE updating the project, then compares the submitted value against this pre-update status. If they differ, it indicates a manual change by the user, and automatic status transitions are skipped to preserve user intent. If they match, automatic business rules still apply (e.g., auto-promoting to PRESUPUESTADO when budget amounts are entered). This fixes the issue where manual status updates in the edit form were being overwritten by automatic business rules.