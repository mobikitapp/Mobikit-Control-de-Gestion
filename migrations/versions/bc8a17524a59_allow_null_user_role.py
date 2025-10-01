"""allow_null_user_role

Revision ID: bc8a17524a59
Revises: 
Create Date: 2025-10-01 19:55:25.701331

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc8a17524a59'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Make the rol column nullable to allow new users without assigned roles
    op.alter_column('users', 'rol',
                    existing_type=sa.Enum('ADMIN', 'GENERAL', 'OPERACIONES', 'VENTAS', 'PRODUCCION', 'LOGISTICA', 'FINANZAS', name='rolusuario'),
                    nullable=True)


def downgrade():
    # Revert rol column back to NOT NULL
    op.alter_column('users', 'rol',
                    existing_type=sa.Enum('ADMIN', 'GENERAL', 'OPERACIONES', 'VENTAS', 'PRODUCCION', 'LOGISTICA', 'FINANZAS', name='rolusuario'),
                    nullable=False)
