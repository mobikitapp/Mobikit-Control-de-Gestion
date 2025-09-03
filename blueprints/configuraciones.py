from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func
from datetime import datetime
from werkzeug.security import generate_password_hash

from app import db
from models import User, RolUsuario
from services.configuraciones_service import ConfiguracionesService
from utils.auth import role_required

# Create blueprint
configuraciones_bp = Blueprint('configuraciones', __name__)

@configuraciones_bp.route('/')
@configuraciones_bp.route('/dashboard')
@login_required
@role_required([RolUsuario.ADMIN])
def dashboard():
    """Dashboard principal de configuraciones"""
    try:
        service = ConfiguracionesService()

        # Get summary statistics
        stats = service.get_configuraciones_stats()

        return render_template('configuraciones/dashboard.html', **stats)

    except Exception as e:
        flash(f'Error al cargar dashboard de configuraciones: {str(e)}', 'error')
        return redirect(url_for('index'))


@configuraciones_bp.route('/usuarios')
@login_required
@role_required([RolUsuario.ADMIN])
def usuarios():
    """Lista de usuarios del sistema"""
    try:
        service = ConfiguracionesService()

        # Get filters from request
        rol = request.args.get('rol')
        busqueda = request.args.get('busqueda', '').strip()
        estado = request.args.get('estado')  # activo/inactivo

        # Get users data
        data = service.get_usuarios_lista(
            rol=rol,
            busqueda=busqueda,
            estado=estado
        )

        return render_template('configuraciones/usuarios.html', **data)

    except Exception as e:
        flash(f'Error al cargar lista de usuarios: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/usuarios/nuevo')
@login_required
@role_required([RolUsuario.ADMIN])
def nuevo_usuario():
    """Formulario para crear nuevo usuario"""
    try:
        service = ConfiguracionesService()

        # Get roles available
        roles = service.get_roles_disponibles()

        return render_template('configuraciones/usuario_form.html',
                             roles=roles, usuario=None, accion='crear')

    except Exception as e:
        flash(f'Error al cargar formulario de usuario: {str(e)}', 'error')
        return redirect(url_for('configuraciones.usuarios'))


@configuraciones_bp.route('/usuarios/nuevo', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def crear_usuario():
    """Crear nuevo usuario"""
    try:
        service = ConfiguracionesService()

        # Get form data
        datos_usuario = {
            'nombre': request.form.get('nombre', '').strip(),
            'apellido': request.form.get('apellido', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telefono': request.form.get('telefono', '').strip(),
            'rol': request.form.get('rol'),
            'activo': request.form.get('activo') == 'on'
        }

        # Validate required fields
        if not all([datos_usuario['nombre'], datos_usuario['email'], datos_usuario['rol']]):
            flash('Nombre, email y rol son obligatorios', 'error')
            return redirect(url_for('configuraciones.nuevo_usuario'))

        # Create user
        success, mensaje = service.crear_usuario(datos_usuario, current_user.id)

        if success:
            flash(f'Usuario {datos_usuario["nombre"]} creado exitosamente', 'success')
            return redirect(url_for('configuraciones.usuarios'))
        else:
            flash(f'Error al crear usuario: {mensaje}', 'error')
            return redirect(url_for('configuraciones.nuevo_usuario'))

    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('configuraciones.usuarios'))


@configuraciones_bp.route('/usuarios/<usuario_id>/editar')
@login_required
@role_required([RolUsuario.ADMIN])
def editar_usuario(usuario_id):
    """Formulario para editar usuario"""
    try:
        service = ConfiguracionesService()

        # Get user data
        usuario = service.get_usuario_by_id(usuario_id)
        if not usuario:
            flash('Usuario no encontrado', 'error')
            return redirect(url_for('configuraciones.usuarios'))

        # Get roles available
        roles = service.get_roles_disponibles()

        return render_template('configuraciones/usuario_form.html',
                             roles=roles, usuario=usuario, accion='editar')

    except Exception as e:
        flash(f'Error al cargar usuario: {str(e)}', 'error')
        return redirect(url_for('configuraciones.usuarios'))


@configuraciones_bp.route('/usuarios/<usuario_id>/editar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_usuario(usuario_id):
    """Actualizar usuario existente"""
    try:
        service = ConfiguracionesService()

        # Get form data
        datos_usuario = {
            'nombre': request.form.get('nombre', '').strip(),
            'apellido': request.form.get('apellido', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telefono': request.form.get('telefono', '').strip(),
            'rol': request.form.get('rol'),
            'activo': request.form.get('activo') == 'on'
        }

        # Validate required fields
        if not all([datos_usuario['nombre'], datos_usuario['email'], datos_usuario['rol']]):
            flash('Nombre, email y rol son obligatorios', 'error')
            return redirect(url_for('configuraciones.editar_usuario', usuario_id=usuario_id))

        # Update user
        success, mensaje = service.actualizar_usuario(usuario_id, datos_usuario, current_user.id)

        if success:
            flash(f'Usuario actualizado exitosamente', 'success')
            return redirect(url_for('configuraciones.usuarios'))
        else:
            flash(f'Error al actualizar usuario: {mensaje}', 'error')
            return redirect(url_for('configuraciones.editar_usuario', usuario_id=usuario_id))

    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('configuraciones.usuarios'))


@configuraciones_bp.route('/usuarios/<usuario_id>/cambiar-estado', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def cambiar_estado_usuario(usuario_id):
    """Activar/desactivar usuario"""
    try:
        service = ConfiguracionesService()

        # Cannot deactivate yourself
        if usuario_id == current_user.id:
            flash('No puedes desactivar tu propio usuario', 'error')
            return redirect(url_for('configuraciones.usuarios'))

        # Change status
        success, mensaje = service.cambiar_estado_usuario(usuario_id, current_user.id)

        if success:
            flash(mensaje, 'success')
        else:
            flash(f'Error: {mensaje}', 'error')

    except Exception as e:
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('configuraciones.usuarios'))


@configuraciones_bp.route('/roles')
@login_required
@role_required([RolUsuario.ADMIN])
def roles():
    """Gestión de roles y permisos"""
    try:
        service = ConfiguracionesService()

        # Get roles data with permissions
        data = service.get_roles_permisos()

        return render_template('configuraciones/roles.html', **data)

    except Exception as e:
        flash(f'Error al cargar roles: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/permisos')
@login_required
@role_required([RolUsuario.ADMIN])
def permisos():
    """Vista detallada de permisos por módulo"""
    try:
        service = ConfiguracionesService()

        # Get permissions matrix
        data = service.get_matriz_permisos()

        return render_template('configuraciones/permisos.html', **data)

    except Exception as e:
        flash(f'Error al cargar permisos: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/sistema')
@login_required
@role_required([RolUsuario.ADMIN])
def configuracion_sistema():
    """Configuración general del sistema"""
    try:
        service = ConfiguracionesService()

        # Get system configuration
        data = service.get_configuracion_sistema()

        return render_template('configuraciones/sistema.html', **data)

    except Exception as e:
        flash(f'Error al cargar configuración del sistema: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


# Routes for commission configuration
@configuraciones_bp.route('/comisiones')
@login_required
@role_required([RolUsuario.ADMIN])
def comisiones():
    """Commission configuration page"""
    try:
        service = ConfiguracionesService()
        data = service.get_comisiones_vendedores()

        return render_template('configuraciones/comisiones.html', **data)

    except Exception as e:
        flash(f'Error al cargar comisiones: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/comisiones/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_comisiones():
    """Update commission settings"""
    try:
        service = ConfiguracionesService()

        # Process form data for each seller
        errores = []
        actualizaciones_exitosas = 0

        for key, value in request.form.items():
            if key.startswith('comision_provision_'):
                vendedor_id = key.replace('comision_provision_', '')
                comision_provision = float(value or 3.0)

                # Get installation commission
                comision_instalacion_key = f'comision_instalacion_{vendedor_id}'
                comision_instalacion = float(request.form.get(comision_instalacion_key, 3.0))

                # Update commission
                success, message = service.actualizar_comision_vendedor(
                    vendedor_id, comision_provision, comision_instalacion, current_user.id
                )

                if success:
                    actualizaciones_exitosas += 1
                else:
                    errores.append(f"Error para vendedor {vendedor_id}: {message}")

        if actualizaciones_exitosas > 0:
            flash(f'Se actualizaron {actualizaciones_exitosas} configuraciones de comisión', 'success')

        if errores:
            for error in errores:
                flash(error, 'error')

        return redirect(url_for('configuraciones.comisiones'))

    except Exception as e:
        flash(f'Error al actualizar comisiones: {str(e)}', 'error')
        return redirect(url_for('configuraciones.comisiones'))


# API Routes
@configuraciones_bp.route('/api/usuarios/<usuario_id>/reset-password', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def api_reset_password(usuario_id):
    """Reset user password"""
    try:
        service = ConfiguracionesService()

        # Generate new password
        success, nueva_password = service.reset_password_usuario(usuario_id, current_user.id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Contraseña restablecida exitosamente',
                'nueva_password': nueva_password
            })
        else:
            return jsonify({
                'success': False,
                'message': nueva_password  # Contains error message
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@configuraciones_bp.route('/api/usuarios/stats')
@login_required
@role_required([RolUsuario.ADMIN])
def api_usuarios_stats():
    """Get user statistics"""
    try:
        service = ConfiguracionesService()

        stats = service.get_usuarios_stats()

        return jsonify({
            'success': True,
            'data': stats
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@configuraciones_bp.route('/api/audit-log')
@login_required
@role_required([RolUsuario.ADMIN])
def api_audit_log():
    """Get audit log for user changes"""
    try:
        service = ConfiguracionesService()

        # Get filters
        limit = request.args.get('limit', 50, type=int)
        usuario_id = request.args.get('usuario_id')
        accion = request.args.get('accion')

        audit_log = service.get_audit_log(limit=limit, usuario_id=usuario_id, accion=accion)

        return jsonify({
            'success': True,
            'data': audit_log
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500