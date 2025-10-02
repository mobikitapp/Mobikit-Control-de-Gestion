from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
import logging

logger = logging.getLogger(__name__)

capacitacion_bp = Blueprint('capacitacion', __name__)

@capacitacion_bp.route('/')
@login_required
def index():
    """Página principal de capacitación"""
    try:
        # Obtener el módulo específico desde la query string
        modulo = request.args.get('modulo', 'introduccion')
        
        return render_template('capacitacion/index.html', 
                             modulo_activo=modulo,
                             title="Capacitación - Sistema de Gestión")
    except Exception as e:
        logger.error(f"Error cargando capacitación: {str(e)}")
        return render_template('capacitacion/index.html', 
                             modulo_activo='introduccion',
                             title="Capacitación - Sistema de Gestión")

@capacitacion_bp.route('/modulo/<modulo_name>')
@login_required 
def modulo(modulo_name):
    """Página específica de un módulo"""
    try:
        modulos_validos = [
            'introduccion', 'flujo-general', 'dashboard', 'clientes', 
            'proyectos', 'contratos', 'fabricacion', 'areas-produccion', 
            'despachos', 'finanzas', 'comercial', 'planificacion-operacional', 
            'calendario', 'configuraciones', 'mejores-practicas'
        ]
        
        if modulo_name not in modulos_validos:
            modulo_name = 'introduccion'
            
        return render_template('capacitacion/index.html',
                             modulo_activo=modulo_name,
                             title=f"Capacitación - {modulo_name.replace('-', ' ').title()}")
    except Exception as e:
        logger.error(f"Error cargando módulo {modulo_name}: {str(e)}")
        return render_template('capacitacion/index.html',
                             modulo_activo='introduccion',
                             title="Capacitación - Sistema de Gestión")