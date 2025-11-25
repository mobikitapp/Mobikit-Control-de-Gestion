# Manufacturing Management System

## Overview
A comprehensive management system for manufacturing companies to centralize the administration of clients, projects, contracts, manufacturing orders, and dispatches. Its purpose is to streamline operations, improve tracking, and enhance decision-making through end-to-end visibility. Key capabilities include integrated document management, quality assurance, multi-role user access, financial payment status, processing time tracking, strategic capacity planning, and customizable project types. The system aims to provide a centralized platform for managing the entire manufacturing lifecycle from client engagement to product delivery.

## Recent Changes
- **November 25, 2025**: Fixed production bug where bulk estado change modal did not display area/estado options. Solution: Pre-render estado options server-side (grouped by area) instead of fetching them asynchronously with JavaScript. This ensures the modal always has options available regardless of network conditions or client-side script execution timing.

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
The system uses a modular blueprint architecture, separating concerns into domain-specific modules, services for business logic, repositories for data access, and Pydantic models for data validation.

### Business Domain Architecture
- **Client Management**: Manages client records, contacts, and project history.
- **Project Lifecycle**: Supports end-to-end project management, including multiple contracts and state management across phases. Features project types (Social, Estandar, Especial) influencing cost and time, and a project log for tracking technical specifications and changes.
- **Contract & Purchase Order Management**: Handles contract/PO-based projects with document attachment, multi-currency support, payment terms, and delivery milestones. Includes a non-destructive archive system.
- **Manufacturing Orders (OF)**: Manages production workflows (planned → in_production → QA → finished → delivered) with material tracking, quality control, and time comparison. Includes bulk operations for multi-selection with checkboxes, allowing mass state changes, archiving, and deletion with partial success handling and role-based permissions. Features project grouping view (default) with project-level checkboxes for batch selection and toggleable flat list view.
- **Dispatch Management**: Coordinates logistics (scheduled → in_transit → delivered → observed) with documentation and evidence collection. Includes a non-destructive archive system.
- **Payment Status System**: Manages financial payment statuses nested under projects, grouped by client, with invoicing functionality and financial analysis.
- **Processing Time Tracking**: Dynamically tracks processing time per area for manufacturing orders.
- **Strategic Capacity Planning**: Provides a system for capacity planning (3-12 months horizon) based on operational parameters and hierarchical demand, including backlog and gap analysis.
- **Productivity Analysis**: Includes orders in "Área Bodega" states for comprehensive metrics.

### Authentication & Authorization
- **Multi-role System**: Supports Admin, Operations, Sales, Production, Logistics roles with granular permissions.
- **Dynamic Permission Management**: Granular permissions by role and module (Read, Create, Edit, Delete) with an administrative interface.
- **Secure Registration**: New users require administrator approval.

### Storage & File Management
- **Standardized Paths**: Organizes files hierarchically (Client/Project).
- **Multiple File Types**: Supports contracts, delivery documentation, and QA evidence.
- **Size Limits**: Configurable upload limits with MIME type validation.

### Database Design
- **Relational Structure**: Normalized schema with foreign key constraints.
- **Audit Fields**: Includes created/updated timestamps and user tracking.
- **State Management**: Uses enum-based status fields, with synchronized enum values across the codebase.
- **Project Enhancements**: Includes `centro_costo` for ERP integration and `bitacora_proyecto` for project logs.

### UI/UX Decisions & Features
- **Responsive Design**: Server-side rendered Jinja2 templates.
- **Visual Indicators**: Utilizes progress bars, status badges, and color-coded indicators.
- **Gantt Chart Enhancements**: Integrates contract milestones and interactive dropdowns for Manufacturing Orders.
- **Print Optimization**: Configured for A4 horizontal and letter format.
- **Notification System**: Separated user notifications from admin configuration with user-specific views and admin-only preferences.
- **Bulk Operations**: Manufacturing orders feature checkbox selection (left column) with floating action bar, confirmation modals, and support for mass state changes, archiving, and deletion. Includes project grouping (default view) with project-header rows and project-level checkboxes that select all OFs within a project, plus a toggle to switch between grouped and flat list views while preserving selection state.

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