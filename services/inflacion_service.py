"""
Servicio para cálculos de efectos inflacionarios en contratos UF
Maneja ganancias/pérdidas por inflación cuando se factura en UF pero se paga en CLP
"""

from decimal import Decimal
from datetime import datetime, date
from typing import Optional, Dict, List, Any
import logging

from models import EstadoPago, TipoEstadoPago, Contrato
from services.uf_conversion_service import UfConversionService
from app import db

logger = logging.getLogger(__name__)

class InflacionService:
    """Servicio para cálculos de efectos inflacionarios UF"""

    @staticmethod
    def calcular_efectos_inflacion_estado(estado_pago: EstadoPago) -> Optional[Dict[str, Any]]:
        """
        Calcula los efectos de inflación para un estado de pago específico
        
        Args:
            estado_pago: Estado de pago a analizar
            
        Returns:
            Dict con información de efectos inflacionarios o None si no aplica
        """
        return estado_pago.efectos_inflacion

    @staticmethod
    def actualizar_ganancias_perdidas_estado(estado_pago: EstadoPago) -> bool:
        """
        Actualiza el campo ganancia_perdida_inflacion basado en los cálculos actuales
        
        Args:
            estado_pago: Estado de pago a actualizar
            
        Returns:
            True si se actualizó, False si no era necesario o falló
        """
        try:
            efectos = estado_pago.efectos_inflacion
            if efectos and 'ganancia_perdida' in efectos:
                estado_pago.ganancia_perdida_inflacion = efectos['ganancia_perdida']
                db.session.commit()
                logger.info(f"Actualizada ganancia/pérdida inflación para estado {estado_pago.id}: {efectos['ganancia_perdida']}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error actualizando efectos inflación para estado {estado_pago.id}: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def calcular_resumen_inflacion_contrato(contrato: Contrato) -> Dict[str, Any]:
        """
        Calcula un resumen de efectos inflacionarios para todo el contrato
        
        Args:
            contrato: Contrato a analizar
            
        Returns:
            Dict con resumen de efectos inflacionarios del contrato
        """
        try:
            resumen = {
                'contrato_id': contrato.id,
                'es_contrato_uf': contrato.moneda_original == 'UF',
                'estados_con_inflacion': [],
                'total_ganancia_perdida': Decimal('0'),
                'total_facturado_uf': Decimal('0'),
                'total_pagado_clp': Decimal('0'),
                'diferencia_uf_actual': Decimal('0')
            }
            
            # Analizar cada estado de pago
            for estado in contrato.estados_pago:
                efectos = estado.efectos_inflacion
                if efectos:
                    estado_info = {
                        'estado_id': estado.id,
                        'tipo_estado': estado.tipo_estado.value,
                        'fecha_estado': estado.fecha_estado,
                        'efectos': efectos
                    }
                    resumen['estados_con_inflacion'].append(estado_info)
                    
                    if estado.ganancia_perdida_inflacion:
                        resumen['total_ganancia_perdida'] += Decimal(str(estado.ganancia_perdida_inflacion))
                
                # Acumular totales
                if estado.tipo_estado == TipoEstadoPago.FACTURADO and estado.monto_uf:
                    resumen['total_facturado_uf'] += Decimal(str(estado.monto_uf))
                elif estado.tipo_estado == TipoEstadoPago.PAGADO and estado.monto:
                    resumen['total_pagado_clp'] += Decimal(str(estado.monto))
            
            # Calcular diferencia UF actual vs contrato original
            if contrato.moneda_original == 'UF' and contrato.monto_total_uf:
                conversion_actual = UfConversionService.convert_uf_to_clp(
                    Decimal(str(contrato.monto_total_uf))
                )
                valor_uf_actual = UfConversionService.get_current_uf_value()
                
                if conversion_actual and contrato.valor_uf_conversion and valor_uf_actual:
                    monto_clp_original = Decimal(str(contrato.monto_total_uf)) * Decimal(str(contrato.valor_uf_conversion))
                    monto_clp_actual = conversion_actual  # convert_uf_to_clp retorna Decimal directamente
                    resumen['diferencia_uf_actual'] = monto_clp_actual - monto_clp_original
                    resumen['valor_uf_contrato'] = contrato.valor_uf_conversion
                    resumen['valor_uf_actual'] = valor_uf_actual
            
            return resumen
            
        except Exception as e:
            logger.error(f"Error calculando resumen inflación para contrato {contrato.id}: {e}")
            return {
                'contrato_id': contrato.id,
                'error': str(e),
                'estados_con_inflacion': [],
                'total_ganancia_perdida': Decimal('0')
            }

    @staticmethod
    def generar_reporte_inflacion(fecha_desde: Optional[date] = None,
                                fecha_hasta: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Genera reporte consolidado de efectos inflacionarios
        
        Args:
            fecha_desde: Fecha inicio del período (opcional)
            fecha_hasta: Fecha fin del período (opcional)
            
        Returns:
            Lista de contratos con sus efectos inflacionarios
        """
        try:
            # Buscar contratos UF con estados de pago en el período
            query = db.session.query(Contrato).filter(
                Contrato.moneda_original == 'UF'
            )
            
            contratos = query.all()
            reporte = []
            
            for contrato in contratos:
                # Filtrar estados por fecha si se especifica
                estados_periodo = contrato.estados_pago
                if fecha_desde or fecha_hasta:
                    estados_periodo = [
                        e for e in contrato.estados_pago 
                        if (not fecha_desde or e.fecha_estado >= fecha_desde) and
                           (not fecha_hasta or e.fecha_estado <= fecha_hasta)
                    ]
                
                if estados_periodo:
                    resumen_contrato = InflacionService.calcular_resumen_inflacion_contrato(contrato)
                    if resumen_contrato['estados_con_inflacion']:
                        resumen_contrato.update({
                            'numero_oc': contrato.numero_oc,
                            'proyecto_nombre': contrato.proyecto.nombre if contrato.proyecto else 'Sin proyecto',
                            'cliente_nombre': contrato.proyecto.cliente.nombre if contrato.proyecto and contrato.proyecto.cliente else 'Sin cliente',
                            'monto_total_uf': contrato.monto_total_uf,
                            'monto_total_clp': contrato.monto_total,
                            'estados_en_periodo': len(estados_periodo)
                        })
                        reporte.append(resumen_contrato)
            
            # Ordenar por ganancia/pérdida descendente
            reporte.sort(key=lambda x: float(x.get('total_ganancia_perdida', 0)), reverse=True)
            
            return reporte
            
        except Exception as e:
            logger.error(f"Error generando reporte inflación: {e}")
            return []

    @staticmethod
    def crear_estado_pago_con_uf(contrato_id: int, 
                               tipo_estado: TipoEstadoPago,
                               monto_uf: Decimal,
                               numero_documento: Optional[str] = None,
                               descripcion: Optional[str] = None,
                               fecha_estado: Optional[date] = None,
                               user_id: Optional[str] = None) -> Optional[EstadoPago]:
        """
        Crea un nuevo estado de pago con cálculos UF automáticos
        
        Args:
            contrato_id: ID del contrato
            tipo_estado: Tipo de estado (FACTURADO, PAGADO, etc.)
            monto_uf: Monto en UF
            numero_documento: Número de documento (factura, etc.)
            descripcion: Descripción del estado
            fecha_estado: Fecha del estado (hoy si no se especifica)
            user_id: ID del usuario que crea el estado
            
        Returns:
            EstadoPago creado o None si falló
        """
        try:
            # Obtener valor UF para la fecha
            if not fecha_estado:
                fecha_estado = date.today()
                
            conversion = UfConversionService.convert_uf_to_clp(monto_uf)
            if not conversion:
                logger.error(f"No se pudo obtener conversión UF para {monto_uf}")
                return None
            
            # Crear estado de pago
            estado = EstadoPago(
                contrato_id=contrato_id,
                tipo_estado=tipo_estado,
                fecha_estado=fecha_estado,
                monto_uf=monto_uf,
                valor_uf_fecha_estado=conversion['valor_uf'],
                monto_clp_equivalente=conversion['clp_amount'],
                monto=conversion['clp_amount'],  # Monto principal en CLP
                moneda_original='UF',
                fecha_conversion_uf=date.today(),
                numero_documento=numero_documento,
                descripcion=descripcion,
                created_by=user_id
            )
            
            db.session.add(estado)
            db.session.commit()
            
            # Actualizar efectos de inflación
            InflacionService.actualizar_ganancias_perdidas_estado(estado)
            
            logger.info(f"Creado estado pago UF {estado.id}: {monto_uf} UF = {conversion['clp_amount']} CLP")
            return estado
            
        except Exception as e:
            logger.error(f"Error creando estado pago UF: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def actualizar_todos_efectos_inflacion() -> Dict[str, int]:
        """
        Actualiza los efectos de inflación para todos los estados de pago UF existentes
        
        Returns:
            Dict con estadísticas de la actualización
        """
        try:
            estados_uf = db.session.query(EstadoPago).filter(
                EstadoPago.moneda_original == 'UF'
            ).all()
            
            actualizados = 0
            errores = 0
            
            for estado in estados_uf:
                if InflacionService.actualizar_ganancias_perdidas_estado(estado):
                    actualizados += 1
                else:
                    errores += 1
            
            logger.info(f"Actualización masiva efectos inflación: {actualizados} actualizados, {errores} errores")
            
            return {
                'total_estados': len(estados_uf),
                'actualizados': actualizados,
                'errores': errores
            }
            
        except Exception as e:
            logger.error(f"Error en actualización masiva efectos inflación: {e}")
            return {
                'total_estados': 0,
                'actualizados': 0,
                'errores': 1,
                'error_message': str(e)
            }