# Manufacturing Management System

## Overview

A comprehensive management system for manufacturing companies that centralizes administration of clients, projects, contracts, manufacturing orders, and dispatches. The system provides complete tracking from initial client contact through project completion and delivery, with integrated document management, quality assurance workflows, and multi-role user access controls.

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
- **Standardized Paths**: Organized storage structure by entity type and purpose
- **Multiple File Types**: Support for contracts, plans, specifications, QA evidence, and delivery documentation
- **Size Limits**: Configurable upload limits (default 25MB) with MIME type validation
- **Audit Trail**: Complete tracking of file uploads, downloads, and modifications

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