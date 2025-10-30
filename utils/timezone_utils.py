
import pytz
from datetime import datetime

# Zona horaria de Chile
CHILE_TZ = pytz.timezone('America/Santiago')

def get_chile_now():
    """Obtener la fecha y hora actual en zona horaria de Chile"""
    return datetime.now(CHILE_TZ)

def convert_to_chile_tz(dt):
    """Convertir datetime a zona horaria de Chile"""
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Asumir UTC si no tiene timezone
        dt = pytz.UTC.localize(dt)
    
    return dt.astimezone(CHILE_TZ)

def format_chile_datetime(dt, format_str='%d/%m/%Y %H:%M'):
    """Formatear datetime en zona horaria de Chile"""
    if dt is None:
        return ''
    
    chile_dt = convert_to_chile_tz(dt)
    return chile_dt.strftime(format_str)

def get_chile_date():
    """Obtener la fecha actual en Chile"""
    return get_chile_now().date()
