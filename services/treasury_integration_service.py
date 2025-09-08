from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from app import db
from models import (Contrato, EstadoPago, PendienteFacturar, TipoDocumento, TipoEstadoPago, 
                    TipoOperacionTesoreria, ModoFacturacion, EstadoPagoContrato as EstadoPagoEnum,
                    EstadoPendienteFacturar)
from services.estados_pago_service import EstadosPagoService
from services.audit_service import AuditService, serialize_model
import logging

logger = logging.getLogger(__name__)

class TreasuryIntegrationService:
    """
    Servicio de integración entre Contratos/OCs y Tesorería
    Maneja la auto-creación y generación inteligente de estados de pago
    """
    
    def __init__(self):
        self.estados_pago_service = EstadosPagoService()

    def process_contract_creation(self, contrato: Contrato, created_by: str) -> List[EstadoPago]:
        """
        Procesa un contrato recién creado y genera automáticamente los estados de pago correspondientes
        
        Args:
            contrato: Contrato recién creado
            created_by: Usuario que crea el contrato
            
        Returns:
            Lista de EstadoPago creados automáticamente
        """
        created_estados = []
        
        try:
            if contrato.tipo_documento == TipoDocumento.ORDEN_COMPRA:
                # Para OCs: Crear en Pendientes de Facturar (flujo simple)
                pendiente_facturar = self._create_oc_as_pending_invoice(contrato, created_by)
                if pendiente_facturar:
                    # Note: PendienteFacturar no se agrega a created_estados (diferente concepto)
                    logger.info(f"OC creada como pendiente de facturar: {pendiente_facturar.id}")
                    
            elif contrato.tipo_documento == TipoDocumento.CONTRATO:
                # Para Contratos: Crear estados de pago según lógica de negocio
                estados_contrato = self._create_contract_payment_states(contrato, created_by)
                created_estados.extend(estados_contrato)
                
            logger.info(f"Procesamiento de contrato {contrato.id} completado. Estados creados: {len(created_estados)}")
            return created_estados
            
        except Exception as e:
            logger.error(f"Error procesando contrato {contrato.id}: {str(e)}")
            raise

    def _create_oc_as_pending_invoice(self, contrato: Contrato, created_by: str) -> Optional[PendienteFacturar]:
        """
        Crea una OC como pendiente de facturar (flujo simple)
        """
        try:
            if not contrato.monto_total or contrato.monto_total <= 0:
                logger.warning(f"OC {contrato.numero_oc} no tiene monto válido para crear como pendiente de facturar")
                return None
                
            # Fecha programada: 30 días desde emisión o desde hoy
            fecha_base = contrato.fecha_emision or date.today()
            fecha_programada = fecha_base + timedelta(days=30)
            
            # Crear registro en Pendientes de Facturar
            pendiente_facturar = PendienteFacturar(
                proyecto_id=contrato.proyecto_id,
                contrato_id=contrato.id,
                numero_oc=contrato.numero_oc,
                monto_neto=contrato.monto_total,
                estado=EstadoPendienteFacturar.PENDIENTE,
                fecha_programada=fecha_programada,
                observaciones=f"OC creada automáticamente desde contrato {contrato.numero_oc}",
                created_by=created_by
            )
            
            db.session.add(pendiente_facturar)
            db.session.commit()
            
            logger.info(f"OC creada como pendiente de facturar: {pendiente_facturar.id} para contrato {contrato.id}")
            return pendiente_facturar
            
        except Exception as e:
            logger.error(f"Error creando OC como pendiente de facturar para contrato {contrato.id}: {str(e)}")
            raise

    def _create_contract_payment_states(self, contrato: Contrato, created_by: str) -> List[EstadoPago]:
        """
        Crea estados de pago para contratos según la lógica de negocio
        """
        estados_creados = []
        
        try:
            # 1. ANTICIPO (solo si anticipo_pct > 0)
            if contrato.anticipo_pct and contrato.anticipo_pct > 0:
                estado_anticipo = self._create_anticipo_state(contrato, created_by)
                if estado_anticipo:
                    estados_creados.append(estado_anticipo)
            
            # 2. Estados según modo de facturación
            if contrato.modo_facturacion == ModoFacturacion.AVANCE:
                # AVANCE_MENSUAL: crear placeholders mensuales
                estados_avance = self._create_monthly_advance_states(contrato, created_by)
                estados_creados.extend(estados_avance)
                
                # LIBERACION_RETENCION: al final si retencion_pct > 0
                if contrato.retencion_pct and contrato.retencion_pct > 0:
                    estado_retencion = self._create_retention_release_state(contrato, created_by)
                    if estado_retencion:
                        estados_creados.append(estado_retencion)
                        
            elif contrato.modo_facturacion == ModoFacturacion.DESPACHO:
                # Solo ANTICIPO si aplica, no crear EPs por defecto
                # Se facturarán contra despachos conformes
                logger.info(f"Contrato {contrato.id} en modo DESPACHO - Solo se creó anticipo si aplica")
            
            return estados_creados
            
        except Exception as e:
            logger.error(f"Error creando estados de pago para contrato {contrato.id}: {str(e)}")
            raise

    def _create_anticipo_state(self, contrato: Contrato, created_by: str) -> Optional[EstadoPago]:
        """Crear estado de pago de ANTICIPO"""
        try:
            monto_anticipo = float(contrato.monto_total or 0) * float(contrato.anticipo_pct or 0) / 100
            
            fecha_programada = contrato.fecha_emision or date.today()
            
            estado_pago = EstadoPago(
                proyecto_id=contrato.proyecto_id,
                contrato_id=contrato.id,
                tipo=TipoEstadoPago.ESTADO_PAGO_CONTRATO,
                descripcion=f"Anticipo {contrato.anticipo_pct}% - {contrato.numero_oc}",
                monto_neto=monto_anticipo,
                monto_estado_pago=monto_anticipo,  # Sin impuestos para simplicidad
                fecha_programada=fecha_programada,
                estado=EstadoPagoEnum.PENDIENTE,
                observaciones=f"Anticipo automático - {contrato.anticipo_pct}% del contrato",
                created_by=created_by
            )
            
            # Agregar campo personalizado para identificar el tipo específico
            estado_pago.notas = f"TIPO_OPERACION:ANTICIPO"
            
            db.session.add(estado_pago)
            db.session.flush()  # Para obtener el ID
            
            logger.info(f"Estado de pago ANTICIPO creado: {estado_pago.id} - Monto: ${monto_anticipo}")
            return estado_pago
            
        except Exception as e:
            logger.error(f"Error creando anticipo para contrato {contrato.id}: {str(e)}")
            raise

    def _create_monthly_advance_states(self, contrato: Contrato, created_by: str) -> List[EstadoPago]:
        """Crear estados de pago mensuales para modo AVANCE"""
        estados = []
        
        try:
            # Estimar duración del proyecto (usar fechas del contrato o default 6 meses)
            fecha_inicio = contrato.fecha_emision or date.today()
            fecha_fin = contrato.fecha_entrega_comprometida 
            
            if not fecha_fin:
                # Default: 6 meses desde inicio
                fecha_fin = fecha_inicio + relativedelta(months=6)
            
            # Calcular número de meses usando relativedelta para precisión
            delta = relativedelta(fecha_fin, fecha_inicio)
            meses_proyecto = delta.years * 12 + delta.months
            
            # Si hay días adicionales, contar como un mes extra
            if delta.days > 0:
                meses_proyecto += 1
                
            # Asegurar mínimo 1 mes
            if meses_proyecto <= 0:
                meses_proyecto = 1
                
            # Crear placeholders mensuales sin monto asignado
            for mes in range(meses_proyecto):
                fecha_periodo = fecha_inicio + relativedelta(months=mes)
                periodo_str = fecha_periodo.strftime('%Y-%m')
                
                estado_pago = EstadoPago(
                    proyecto_id=contrato.proyecto_id,
                    contrato_id=contrato.id,
                    tipo=TipoEstadoPago.ESTADO_PAGO_CONTRATO,
                    descripcion=f"Avance Mensual {periodo_str} - {contrato.numero_oc}",
                    monto_neto=0,  # Se calcula al certificar
                    monto_estado_pago=0,
                    fecha_programada=fecha_periodo + relativedelta(day=31),  # Último día del mes
                    estado=EstadoPagoEnum.PENDIENTE,
                    observaciones=f"Avance mensual - Período {periodo_str}. Monto se calcula al certificar.",
                    created_by=created_by
                )
                
                estado_pago.notas = f"TIPO_OPERACION:AVANCE_MENSUAL|PERIODO:{periodo_str}"
                
                db.session.add(estado_pago)
                db.session.flush()
                estados.append(estado_pago)
            
            logger.info(f"Estados de avance mensual creados: {len(estados)} para contrato {contrato.id}")
            return estados
            
        except Exception as e:
            logger.error(f"Error creando estados mensuales para contrato {contrato.id}: {str(e)}")
            raise

    def _create_retention_release_state(self, contrato: Contrato, created_by: str) -> Optional[EstadoPago]:
        """Crear estado de pago para LIBERACION_RETENCION"""
        try:
            monto_retencion = float(contrato.monto_total or 0) * float(contrato.retencion_pct or 0) / 100
            
            # Fecha programada: al final del proyecto + 30 días
            fecha_base = contrato.fecha_entrega_comprometida or date.today() + relativedelta(months=6)
            fecha_programada = fecha_base + timedelta(days=30)
            
            estado_pago = EstadoPago(
                proyecto_id=contrato.proyecto_id,
                contrato_id=contrato.id,
                tipo=TipoEstadoPago.ESTADO_PAGO_CONTRATO,
                descripcion=f"Liberación Retención {contrato.retencion_pct}% - {contrato.numero_oc}",
                monto_neto=monto_retencion,
                monto_estado_pago=monto_retencion,
                fecha_programada=fecha_programada,
                estado=EstadoPagoEnum.PENDIENTE,
                observaciones=f"Liberación automática de retención - {contrato.retencion_pct}% del contrato",
                created_by=created_by
            )
            
            estado_pago.notas = f"TIPO_OPERACION:LIBERACION_RETENCION"
            
            db.session.add(estado_pago)
            db.session.flush()
            
            logger.info(f"Estado de liberación de retención creado: {estado_pago.id} - Monto: ${monto_retencion}")
            return estado_pago
            
        except Exception as e:
            logger.error(f"Error creando liberación de retención para contrato {contrato.id}: {str(e)}")
            raise

    def get_contracts_without_treasury_states(self) -> List[Dict[str, Any]]:
        """
        Obtiene CONTRATOS que no tienen estados de pago en tesorería y podrían necesitarlos
        (Las OCs van a PendienteFacturar, no a EstadoPago)
        """
        try:
            # Solo buscar CONTRATOS sin estados de pago (las OCs van a otro lado)
            contratos_sin_estados = db.session.query(Contrato).filter(
                Contrato.estado.in_(['VIGENTE', 'BORRADOR']),
                Contrato.tipo_documento == TipoDocumento.CONTRATO,  # Solo contratos
                ~Contrato.id.in_(
                    db.session.query(EstadoPago.contrato_id).filter(
                        EstadoPago.contrato_id.isnot(None)
                    )
                )
            ).all()
            
            resultado = []
            for contrato in contratos_sin_estados:
                resultado.append({
                    'contrato': contrato,
                    'puede_auto_crear': False,  # Los contratos requieren revisión manual
                    'requiere_manual': True,    # Siempre manual para contratos
                    'tiene_anticipo': contrato.anticipo_pct and contrato.anticipo_pct > 0,
                    'modo_facturacion': contrato.modo_facturacion.value if contrato.modo_facturacion else None
                })
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo contratos sin estados de tesorería: {str(e)}")
            return []

    def create_states_for_existing_contract(self, contrato_id: int, created_by: str) -> List[EstadoPago]:
        """
        Crea estados de pago para un contrato existente (uso manual desde la interfaz)
        """
        try:
            contrato = Contrato.query.get(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")
            
            # Verificar si ya tiene estados de pago
            existing_states = EstadoPago.query.filter_by(contrato_id=contrato_id).count()
            if existing_states > 0:
                logger.warning(f"Contrato {contrato_id} ya tiene {existing_states} estados de pago")
                return []
            
            # Procesar según tipo de documento
            return self.process_contract_creation(contrato, created_by)
            
        except Exception as e:
            logger.error(f"Error creando estados para contrato existente {contrato_id}: {str(e)}")
            raise

    def get_pending_invoices(self) -> List[PendienteFacturar]:
        """
        Obtiene todas las OCs pendientes de facturar
        """
        try:
            return PendienteFacturar.query.filter(
                PendienteFacturar.estado.in_([
                    EstadoPendienteFacturar.PENDIENTE, 
                    EstadoPendienteFacturar.FACTURADO
                ])
            ).order_by(PendienteFacturar.fecha_programada.asc()).all()
            
        except Exception as e:
            logger.error(f"Error obteniendo pendientes de facturar: {str(e)}")
            return []

    def update_pending_invoice_status(self, pendiente_id: int, nuevo_estado: EstadoPendienteFacturar, 
                                    updated_by: str, numero_factura: str = None) -> bool:
        """
        Actualiza el estado de un pendiente de facturar
        """
        try:
            pendiente = PendienteFacturar.query.get(pendiente_id)
            if not pendiente:
                return False
            
            # Actualizar estado
            pendiente.estado = nuevo_estado
            pendiente.updated_by = updated_by
            pendiente.updated_at = datetime.utcnow()
            
            # Actualizar fechas según el estado
            if nuevo_estado == EstadoPendienteFacturar.FACTURADO:
                pendiente.fecha_facturado = date.today()
                if numero_factura:
                    pendiente.numero_factura = numero_factura
                    
            elif nuevo_estado == EstadoPendienteFacturar.PAGADO:
                if not pendiente.fecha_facturado:
                    pendiente.fecha_facturado = date.today()  # Auto-mark as invoiced
                pendiente.fecha_pagado = date.today()
            
            db.session.add(pendiente)
            db.session.commit()
            
            logger.info(f"Estado de pendiente facturar actualizado: {pendiente_id} -> {nuevo_estado.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando estado de pendiente facturar {pendiente_id}: {str(e)}")
            return False