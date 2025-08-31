
#!/usr/bin/env python3
"""
Script para crear usuario administrador
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def create_admin_user():
    """Convierte un usuario en administrador"""
    if not DATABASE_URL:
        print("DATABASE_URL environment variable not set")
        return
    
    # Pide el ID del usuario de Replit
    user_id = input("Ingresa el User ID de Replit (aparece en X-Replit-User-Id): ")
    if not user_id:
        print("User ID es requerido")
        return
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        # Verifica si el usuario existe
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user:
            # Actualiza rol a admin
            cursor.execute(
                "UPDATE users SET rol = 'admin', activo = TRUE WHERE id = %s",
                (user_id,)
            )
            print(f"✓ Usuario {user['first_name']} {user['last_name']} es ahora administrador")
        else:
            # Crea nuevo usuario admin
            email = input("Email del usuario: ")
            first_name = input("Nombre: ")
            last_name = input("Apellido: ")
            
            cursor.execute("""
                INSERT INTO users (id, email, first_name, last_name, rol, activo)
                VALUES (%s, %s, %s, %s, 'admin', TRUE)
                ON CONFLICT (id) DO UPDATE SET
                    rol = 'admin',
                    activo = TRUE
            """, (user_id, email, first_name, last_name))
            
            print(f"✓ Usuario administrador creado: {first_name} {last_name}")
        
        conn.commit()
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    create_admin_user()
