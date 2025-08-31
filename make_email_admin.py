
#!/usr/bin/env python3
"""
Script para hacer admin a mobikitapp@gmail.com
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def make_email_admin():
    """Convierte mobikitapp@gmail.com en administrador"""
    if not DATABASE_URL:
        print("DATABASE_URL environment variable not set")
        return
    
    email = "mobikitapp@gmail.com"
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        # Buscar usuario por email
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user:
            # Actualizar rol a admin
            cursor.execute(
                "UPDATE users SET rol = 'admin', activo = TRUE WHERE email = %s",
                (email,)
            )
            print(f"✓ Usuario {user['first_name']} {user['last_name']} ({email}) es ahora administrador")
        else:
            print(f"✗ No se encontró usuario con email {email}")
            print("El usuario debe autenticarse al menos una vez antes de poder ser convertido en admin")
        
        conn.commit()
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    make_email_admin()
