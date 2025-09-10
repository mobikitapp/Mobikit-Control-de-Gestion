from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func
from datetime import datetime
from werkzeug.security import generate_password_hash

from app import db
from models import User, RolUsuario
from services.configuraciones_service import ConfiguracionesService
from services.permisos_service import PermisosService
from utils.auth import role_required
from models import NotificationPreferences, TipoNotificacion

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


@configuraciones_bp.route('/actualizar-factores', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_factores():
    """Actualizar factores de tiempo de configuración"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        factor_fabrica = data.get('factor_tiempo_fabrica')
        factor_embalaje = data.get('factor_tiempo_embalaje')

        # Validate inputs
        if factor_fabrica is None or factor_embalaje is None:
            return jsonify({'error': 'Faltan datos requeridos'}), 400

        if not (0 <= factor_fabrica <= 1) or not (0 <= factor_embalaje <= 1):
            return jsonify({'error': 'Los factores deben estar entre 0 y 1'}), 400

        service = ConfiguracionesService()
        success = service.actualizar_factores_tiempo(
            factor_fabrica=factor_fabrica,
            factor_embalaje=factor_embalaje,
            usuario_id=current_user.id
        )

        if success:
            return jsonify({
                'message': 'Factores de tiempo actualizados correctamente',
                'factor_tiempo_fabrica': factor_fabrica,
                'factor_tiempo_embalaje': factor_embalaje
            })
        else:
            return jsonify({'error': 'Error interno al actualizar factores'}), 500

    except Exception as e:
        return jsonify({'error': f'Error al actualizar factores: {str(e)}'}), 500


@configuraciones_bp.route('/actualizar-capacidad', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_capacidad():
    """Actualizar configuración de capacidad"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        # Extract capacity data
        capacidad_data = {
            'capacidad_maxima_tableros_mes': data.get('capacidad_maxima_tableros_mes'),
            'capacidad_maxima_tableros_semana': data.get('capacidad_maxima_tableros_semana'),
            'horas_disponibles_mes': data.get('horas_disponibles_mes'),
            'horas_disponibles_semana': data.get('horas_disponibles_semana'),
            'horas_por_tablero_social': data.get('horas_por_tablero_social'),
            'horas_por_tablero_estandar': data.get('horas_por_tablero_estandar'),
            'horas_por_tablero_especial': data.get('horas_por_tablero_especial'),
        }

        # Validate all required fields are present and positive
        for key, value in capacidad_data.items():
            if value is None:
                return jsonify({'error': f'Falta el campo requerido: {key}'}), 400
            if value <= 0:
                return jsonify({'error': f'El valor de {key} debe ser mayor a 0'}), 400

        service = ConfiguracionesService()
        success = service.actualizar_configuracion_capacidad(capacidad_data, current_user.id)

        if success:
            return jsonify({
                'message': 'Configuración de capacidad actualizada correctamente',
                'data': capacidad_data
            })
        else:
            return jsonify({'error': 'Error interno al actualizar configuración de capacidad'}), 500

    except Exception as e:
        return jsonify({'error': f'Error al actualizar capacidad: {str(e)}'}), 500


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


# =============================================================================
# GESTIÓN DINÁMICA DE PERMISOS
# =============================================================================

@configuraciones_bp.route('/permisos/gestionar')
@login_required
@role_required([RolUsuario.ADMIN])
def gestionar_permisos():
    """Interfaz principal para gestión dinámica de permisos"""
    try:
        service = PermisosService()

        # Obtener matriz completa de permisos
        data = service.obtener_matriz_permisos_completa()

        if data['success']:
            # Convertir la matriz para JavaScript
            import json
            data['matriz_json'] = json.dumps(data['matriz'])
            return render_template('configuraciones/gestionar_permisos.html', **data)
        else:
            flash(f'Error al cargar permisos: {data["error"]}', 'error')
            return redirect(url_for('configuraciones.dashboard'))

    except Exception as e:
        flash(f'Error al cargar gestión de permisos: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/permisos/inicializar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def inicializar_permisos():
    """Inicializa el sistema de permisos dinámicos"""
    try:
        service = PermisosService()
        success, mensaje = service.inicializar_modulos_sistema(current_user.id)

        if success:
            flash(mensaje, 'success')
        else:
            flash(f'Error: {mensaje}', 'error')

    except Exception as e:
        flash(f'Error al inicializar permisos: {str(e)}', 'error')

    return redirect(url_for('configuraciones.gestionar_permisos'))


@configuraciones_bp.route('/permisos/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_permiso_individual():
    """Actualiza un permiso específico"""
    try:
        service = PermisosService()

        # Obtener datos del formulario
        rol = request.form.get('rol')
        modulo = request.form.get('modulo')
        tipo_permiso = request.form.get('tipo_permiso')
        permitido = request.form.get('permitido') == 'true'

        if not all([rol, modulo, tipo_permiso]):
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            }), 400

        success, mensaje = service.actualizar_permiso(
            rol, modulo, tipo_permiso, permitido, current_user.id
        )

        if success:
            return jsonify({
                'success': True,
                'message': mensaje
            })
        else:
            return jsonify({
                'success': False,
                'message': mensaje
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error individual: {str(e)}'
        }), 500


@configuraciones_bp.route('/permisos/actualizar-masivo', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def actualizar_permisos_masivo():
    """Actualiza múltiples permisos en una sola operación"""
    try:
        service = PermisosService()

        # Obtener datos JSON del cuerpo de la solicitud
        data = request.get_json()
        if not data or 'updates' not in data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos de actualización'
            }), 400

        updates = data['updates']
        if not isinstance(updates, list):
            return jsonify({
                'success': False,
                'message': 'Los datos de actualización deben ser una lista'
            }), 400

        success, resultado = service.actualizar_permisos_masivo(updates, current_user.id)

        if success:
            return jsonify({
                'success': True,
                'data': resultado
            })
        else:
            return jsonify({
                'success': False,
                'message': str(resultado)
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error masivo: {str(e)}'
        }), 500


@configuraciones_bp.route('/permisos/resetear-rol', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def resetear_permisos_rol():
    """Resetea todos los permisos de un rol a los valores por defecto"""
    try:
        service = PermisosService()

        rol = request.form.get('rol')
        if not rol:
            return jsonify({
                'success': False,
                'message': 'Rol requerido'
            }), 400

        success, mensaje = service.resetear_permisos_rol(rol, current_user.id)

        if success:
            return jsonify({
                'success': True,
                'message': mensaje
            })
        else:
            return jsonify({
                'success': False,
                'message': mensaje
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error resetear: {str(e)}'
        }), 500


@configuraciones_bp.route('/api/permisos/matriz')
@login_required
@role_required([RolUsuario.ADMIN])
def api_obtener_matriz_permisos():
    """API para obtener la matriz completa de permisos"""
    try:
        service = PermisosService()
        data = service.obtener_matriz_permisos_completa()

        if data['success']:
            return jsonify({
                'success': True,
                'data': data
            })
        else:
            return jsonify({
                'success': False,
                'message': data['error']
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error matriz: {str(e)}'
        }), 500


@configuraciones_bp.route('/api/permisos/auditoria')
@login_required
@role_required([RolUsuario.ADMIN])
def api_auditoria_permisos():
    """API para obtener el historial de cambios en permisos"""
    try:
        service = PermisosService()

        # Obtener filtros
        limit = request.args.get('limit', 50, type=int)
        rol_filtro = request.args.get('rol')
        modulo_filtro = request.args.get('modulo')

        data = service.obtener_auditoria_permisos(
            limit=limit,
            rol_filtro=rol_filtro,
            modulo_filtro=modulo_filtro
        )

        if data['success']:
            return jsonify({
                'success': True,
                'data': data['auditorias']
            })
        else:
            return jsonify({
                'success': False,
                'message': data['error']
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error auditoria: {str(e)}'
        }), 500


@configuraciones_bp.route('/permisos/auditoria')
@login_required
@role_required([RolUsuario.ADMIN])
def ver_auditoria_permisos():
    """Vista para el historial de cambios en permisos"""
    try:
        service = PermisosService()

        # Obtener historial inicial
        data = service.obtener_auditoria_permisos(limit=50)

        if data['success']:
            return render_template('configuraciones/auditoria_permisos.html',
                                 auditorias=data['auditorias'])
        else:
            flash(f'Error al cargar auditoría: {data["error"]}', 'error')
            return redirect(url_for('configuraciones.dashboard'))

    except Exception as e:
        flash(f'Error al cargar auditoría de permisos: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/limpiar-cache', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def limpiar_cache():
    """Endpoint para limpiar caché de la aplicación"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Iniciando limpieza de caché...")
        
        # Limpiar caché de Python (garbage collection)
        import gc
        collected = gc.collect()
        logger.info(f"Garbage collection ejecutado: {collected} objetos limpiados")

        # Limpiar archivos temporales específicos de la aplicación
        import tempfile
        import shutil
        import os
        temp_dir = tempfile.gettempdir()
        
        temp_files_cleaned = 0
        try:
            # Buscar archivos temporales de la aplicación
            for filename in os.listdir(temp_dir):
                if any(pattern in filename.lower() for pattern in ['flask', 'werkzeug', 'tmp_', 'cache_']):
                    try:
                        file_path = os.path.join(temp_dir, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            temp_files_cleaned += 1
                    except PermissionError:
                        # Archivo en uso, continuar con el siguiente
                        continue
            logger.info(f"Archivos temporales limpiados: {temp_files_cleaned}")
        except Exception as temp_error:
            logger.warning(f"No se pudieron limpiar algunos archivos temporales: {temp_error}")

        # Limpiar caché de SQLAlchemy
        from app import db
        try:
            # Cerrar todas las sesiones activas
            db.session.close()
            # Limpiar el pool de conexiones
            db.engine.dispose()
            logger.info("Caché de SQLAlchemy limpiado")
        except Exception as db_error:
            logger.warning(f"Error limpiando caché de base de datos: {db_error}")

        # Limpiar variables de entorno temporales si existen
        import sys
        modules_before = len(sys.modules)
        # No eliminar módulos críticos, solo limpiar referencias
        gc.collect()  # Segunda pasada de garbage collection
        modules_after = len(sys.modules)
        logger.info(f"Módulos en memoria: {modules_before} -> {modules_after}")

        success_message = f'Caché limpiada exitosamente. GC: {collected} objetos, Archivos temp: {temp_files_cleaned}'
        flash(success_message, 'success')
        logger.info("Limpieza de caché completada exitosamente")

        return jsonify({
            'success': True,
            'message': success_message,
            'details': {
                'garbage_collected': collected,
                'temp_files_cleaned': temp_files_cleaned,
                'modules_count': modules_after
            }
        })

    except Exception as e:
        error_msg = f'Error al limpiar caché: {str(e)}'
        logger.error(error_msg, exc_info=True)
        flash(error_msg, 'error')
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@configuraciones_bp.route('/limpiar-datos', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN])
def limpiar_datos():
    """Endpoint para limpiar todos los datos de producción"""
    try:
        from app import db
        from sqlalchemy import text
        import logging
        logger = logging.getLogger(__name__)

        # Ejecutar la limpieza usando SQLAlchemy
        with db.engine.connect() as conn:
            with conn.begin():
                logger.info("Iniciando limpieza de datos de producción...")

                # 1. Eliminar dependencias de órdenes de fabricación
                logger.info("Eliminando items de órdenes de fabricación...")
                conn.execute(text("DELETE FROM of_items"))

                logger.info("Eliminando progreso de áreas...")
                conn.execute(text("DELETE FROM orden_area_progreso"))

                logger.info("Eliminando detalles de despacho...")
                conn.execute(text("DELETE FROM despacho_ordenes_fabricacion"))

                # 2. Eliminar órdenes de fabricación
                logger.info("Eliminando órdenes de fabricación...")
                conn.execute(text("DELETE FROM ordenes_fabricacion"))

                # 3. Eliminar adjuntos de despachos
                logger.info("Eliminando adjuntos de despachos...")
                conn.execute(text("DELETE FROM despacho_adjuntos"))

                # 4. Eliminar despachos
                logger.info("Eliminando despachos...")
                conn.execute(text("DELETE FROM despachos"))

                # 5. Eliminar hitos de entrega y planes
                logger.info("Eliminando eventos de entrega...")
                conn.execute(text("DELETE FROM eventos_entrega"))

                logger.info("Eliminando hitos de entrega...")
                conn.execute(text("DELETE FROM hitos_entrega"))

                logger.info("Eliminando planes de entrega...")
                conn.execute(text("DELETE FROM planes_entrega"))

                # 6. Eliminar adjuntos de contratos
                logger.info("Eliminando adjuntos de contratos...")
                conn.execute(text("DELETE FROM contrato_adjuntos"))

                # 7. Eliminar estados de pago
                logger.info("Eliminando estados de pago...")
                conn.execute(text("DELETE FROM estados_pago"))

                logger.info("Eliminando pendientes de facturar...")
                conn.execute(text("DELETE FROM pendientes_facturar"))

                # 8. Eliminar entregas de contrato
                logger.info("Eliminando entregas de contrato...")
                conn.execute(text("DELETE FROM contrato_entregas"))

                # 9. Limpiar relaciones de categorías de contratos
                logger.info("Eliminando categorías de contratos...")
                conn.execute(text("DELETE FROM contrato_categorias"))

                # 10. Eliminar contratos
                logger.info("Eliminando contratos...")
                conn.execute(text("DELETE FROM contratos"))

                # 11. Eliminar tareas comerciales
                logger.info("Eliminando tareas comerciales...")
                conn.execute(text("DELETE FROM tareas_comerciales"))

                # 12. Eliminar adjuntos de proyectos
                logger.info("Eliminando adjuntos de proyectos...")
                conn.execute(text("DELETE FROM proyecto_adjuntos"))

                # 13. Limpiar relaciones de categorías de proyectos
                logger.info("Eliminando categorías de proyectos...")
                conn.execute(text("DELETE FROM proyecto_categorias"))

                # 14. Resetear estados de proyectos
                logger.info("Reseteando estados de proyectos...")
                conn.execute(text("""
                    UPDATE proyectos 
                    SET estado_comercial = 'PENDIENTE_PRESUPUESTO',
                        fecha_fin_real = NULL,
                        fecha_adjudicacion = NULL,
                        updated_at = CURRENT_TIMESTAMP
                """))

                # 15. Limpiar auditoría relacionada
                logger.info("Limpiando registros de auditoría...")
                conn.execute(text("""
                    DELETE FROM audit_log 
                    WHERE entidad IN ('ordenes_fabricacion', 'contratos', 'despachos', 'estados_pago')
                """))

                # 16. Resetear secuencias si existen
                logger.info("Reseteando secuencias...")
                try:
                    sequences = [
                        "ordenes_fabricacion_id_seq",
                        "contratos_id_seq", 
                        "despachos_id_seq",
                        "estados_pago_id_seq",
                        "pendientes_facturar_id_seq"
                    ]
                    for seq in sequences:
                        try:
                            conn.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                        except Exception:
                            pass  # Secuencia no existe
                except Exception as e:
                    logger.warning(f"No se pudieron resetear secuencias: {e}")

                logger.info("Limpieza de datos completada exitosamente")

        flash('Datos de producción limpiados exitosamente', 'success')
        return jsonify({
            'success': True,
            'message': 'Datos de producción limpiados exitosamente. Los proyectos permanecen activos pero sin órdenes asociadas.'
        })

    except Exception as e:
        # Asegurar imports en caso de error
        import logging
        from app import db
        logger = logging.getLogger(__name__)
        
        error_msg = f"Error al limpiar datos de producción: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Intentar rollback si hay una transacción activa
        try:
            db.session.rollback()
        except Exception:
            pass
            
        flash(error_msg, 'error')
        return jsonify({
            'success': False,
            'message': error_msg,
            'error_type': type(e).__name__
        }), 500


# =============================================================================
# PREFERENCIAS DE NOTIFICACIONES
# =============================================================================

@configuraciones_bp.route('/notificaciones')
@login_required
def notificaciones():
    """Panel de configuración de notificaciones del usuario"""
    try:
        # Get or create user notification preferences
        preferences = NotificationPreferences.query.filter_by(user_id=current_user.id).first()
        
        if not preferences:
            # Create default preferences
            preferences = NotificationPreferences(
                user_id=current_user.id,
                nuevo_proyecto_email=True,
                comentario_bitacora_email=True,
                cambio_estado_of_email=True,
                vencimiento_contrato_email=True,
                retraso_proyecto_email=True,
                email_enabled=True
            )
            db.session.add(preferences)
            db.session.commit()
        
        # Get notification types for template
        tipos_notificacion = {
            'nuevo_proyecto': {
                'nombre': 'Nuevos Proyectos',
                'descripcion': 'Notificaciones cuando se crean nuevos proyectos',
                'habilitado': preferences.nuevo_proyecto_email
            },
            'comentario_bitacora': {
                'nombre': 'Comentarios en Bitácora',
                'descripcion': 'Notificaciones cuando se agregan comentarios a proyectos',
                'habilitado': preferences.comentario_bitacora_email
            },
            'cambio_estado_of': {
                'nombre': 'Cambios de Estado OF',
                'descripcion': 'Notificaciones cuando cambia el estado de órdenes de fabricación',
                'habilitado': preferences.cambio_estado_of_email
            },
            'vencimiento_contrato': {
                'nombre': 'Vencimientos de Contrato',
                'descripcion': 'Alertas de contratos próximos a vencer',
                'habilitado': preferences.vencimiento_contrato_email
            },
            'retraso_proyecto': {
                'nombre': 'Retrasos en Proyectos',
                'descripcion': 'Alertas cuando un proyecto se atrasa',
                'habilitado': preferences.retraso_proyecto_email
            }
        }
        
        return render_template('configuraciones/notificaciones.html', 
                             preferences=preferences,
                             tipos_notificacion=tipos_notificacion)
        
    except Exception as e:
        flash(f'Error al cargar preferencias de notificaciones: {str(e)}', 'error')
        return redirect(url_for('configuraciones.dashboard'))


@configuraciones_bp.route('/notificaciones', methods=['POST'])
@login_required
def actualizar_notificaciones():
    """Actualizar preferencias de notificaciones del usuario"""
    try:
        # Get or create user notification preferences
        preferences = NotificationPreferences.query.filter_by(user_id=current_user.id).first()
        
        if not preferences:
            preferences = NotificationPreferences(user_id=current_user.id)
            db.session.add(preferences)
        
        # Update preferences from form
        preferences.email_enabled = 'email_enabled' in request.form
        preferences.nuevo_proyecto_email = 'nuevo_proyecto_email' in request.form
        preferences.comentario_bitacora_email = 'comentario_bitacora_email' in request.form
        preferences.cambio_estado_of_email = 'cambio_estado_of_email' in request.form
        preferences.vencimiento_contrato_email = 'vencimiento_contrato_email' in request.form
        preferences.retraso_proyecto_email = 'retraso_proyecto_email' in request.form
        preferences.updated_at = datetime.now()
        
        db.session.commit()
        flash('Preferencias de notificaciones actualizadas exitosamente', 'success')
        
        return redirect(url_for('configuraciones.notificaciones'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar preferencias: {str(e)}', 'error')
        return redirect(url_for('configuraciones.notificaciones'))