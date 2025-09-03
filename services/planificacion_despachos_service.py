from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import and_, or_, func, desc, asc
from models import (
    Cliente, Proyecto, Contrato, HitoEntrega, Despacho, 
    OrdenFabricacion, DespachoOrdenFabricacion,
    EstadoHitoEntrega, EstadoOF, EstadoBodega, TipoDespacho
)
from schemas.despachos import (
    ClienteConProyectos, ProyectoConHitos, HitoEntregaDespacho,
    PlanificacionDespachosResponse
)
from app import db
import logging

logger = logging.getLogger(__name__)

class PlanificacionDespachosService:
    """Servicio para la planificación de despachos basada en hitos de entrega"""
    
    @staticmethod
    def get_vista_planificacion() -> PlanificacionDespachosResponse:
        """
        Obtiene la vista principal de planificación de despachos
        organizada por Cliente → Proyecto → Hitos de Entrega
        """
        try:
            # Obtener hitos de entrega pendientes con sus proyectos y clientes
            from models import PlanEntrega, Contrato
            hitos_query = db.session.query(HitoEntrega).join(
                PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id
            ).join(
                Contrato, PlanEntrega.contrato_id == Contrato.id
            ).join(
                Proyecto, Contrato.proyecto_id == Proyecto.id
            ).join(
                Cliente, Proyecto.cliente_id == Cliente.id
            ).filter(
                HitoEntrega.estado.in_([EstadoHitoEntrega.PENDIENTE, EstadoHitoEntrega.ATRASADO])
            ).options(
                selectinload(HitoEntrega.plan_entrega)
                .selectinload(PlanEntrega.contrato)
                .selectinload(Contrato.proyecto)
                .selectinload(Proyecto.cliente),
                selectinload(HitoEntrega.despachos)
            ).order_by(
                Cliente.nombre,
                Proyecto.nombre,
                HitoEntrega.fecha_programada
            ).all()
            
            # Organizar datos por cliente
            clientes_dict: Dict[int, Dict[str, Any]] = {}
            total_hitos_pendientes = 0
            total_hitos_proximos = 0
            fecha_limite_proximos = date.today() + timedelta(days=7)
            
            for hito in hitos_query:
                cliente = hito.plan_entrega.contrato.proyecto.cliente
                proyecto = hito.plan_entrega.contrato.proyecto
                
                # Contar totales
                total_hitos_pendientes += 1
                if hito.fecha_programada <= fecha_limite_proximos:
                    total_hitos_proximos += 1
                
                # Organizar por cliente
                if cliente.id not in clientes_dict:
                    clientes_dict[cliente.id] = {
                        'id': cliente.id,
                        'nombre': cliente.nombre,
                        'proyectos': {}
                    }
                
                # Organizar por proyecto
                if proyecto.id not in clientes_dict[cliente.id]['proyectos']:
                    clientes_dict[cliente.id]['proyectos'][proyecto.id] = {
                        'id': proyecto.id,
                        'nombre': proyecto.nombre,
                        'hitos_entrega': []
                    }
                
                # Verificar si ya tiene despacho creado
                despacho_creado = len(hito.despachos) > 0
                despacho_id = hito.despachos[0].id if despacho_creado else None
                
                # Obtener OFs disponibles para este hito
                ofs_disponibles = PlanificacionDespachosService._get_ofs_disponibles_para_hito(hito.id)
                
                # Crear datos del hito
                hito_data = {
                    'id': hito.id,
                    'contrato_id': hito.plan_entrega.contrato_id,
                    'contrato_numero_oc': hito.plan_entrega.contrato.numero_oc,
                    'descripcion': hito.descripcion,
                    'fecha_entrega': hito.fecha_programada,
                    'estado': hito.estado.value,
                    'despacho_creado': despacho_creado,
                    'despacho_id': despacho_id,
                    'ordenes_fabricacion_disponibles': ofs_disponibles
                }
                
                clientes_dict[cliente.id]['proyectos'][proyecto.id]['hitos_entrega'].append(hito_data)
            
            # Convertir a formato de respuesta
            clientes_response = []
            for cliente_data in clientes_dict.values():
                proyectos_response = []
                for proyecto_data in cliente_data['proyectos'].values():
                    proyectos_response.append(ProyectoConHitos(
                        id=proyecto_data['id'],
                        nombre=proyecto_data['nombre'],
                        hitos_entrega=[HitoEntregaDespacho(**hito) for hito in proyecto_data['hitos_entrega']]
                    ))
                
                clientes_response.append(ClienteConProyectos(
                    id=cliente_data['id'],
                    nombre=cliente_data['nombre'],
                    proyectos=proyectos_response
                ))
            
            return PlanificacionDespachosResponse(
                clientes=clientes_response,
                total_hitos_pendientes=total_hitos_pendientes,
                total_hitos_proximos=total_hitos_proximos
            )
            
        except Exception as e:
            logger.error(f"Error obteniendo vista de planificación: {str(e)}")
            raise Exception(f"Error obteniendo vista de planificación: {str(e)}")
    
    @staticmethod
    def _get_ofs_disponibles_para_hito(hito_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene las órdenes de fabricación disponibles para un hito específico
        """
        try:
            # Obtener el hito con sus relaciones
            from models import PlanEntrega, Contrato
            hito = db.session.query(HitoEntrega).options(
                selectinload(HitoEntrega.plan_entrega).selectinload(PlanEntrega.contrato).selectinload(Contrato.proyecto)
            ).filter_by(id=hito_id).first()
            if not hito:
                return []
            
            # Obtener OFs del proyecto que estén listas para despacho
            from models import OrdenAreaProgreso, Area, AreaEstado, TipoArea
            ofs = db.session.query(OrdenFabricacion).join(
                OrdenAreaProgreso, OrdenFabricacion.id == OrdenAreaProgreso.orden_fabricacion_id
            ).join(
                Area, OrdenAreaProgreso.area_id == Area.id
            ).join(
                AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id
            ).filter(
                OrdenFabricacion.proyecto_id == hito.plan_entrega.contrato.proyecto_id,
                OrdenAreaProgreso.es_actual == True,
                Area.tipo == TipoArea.BODEGA,
                AreaEstado.codigo == 'listo_para_despacho'
            ).all()
            
            ofs_disponibles = []
            for of in ofs:
                # Calcular cantidad total y cantidad ya despachada
                cantidad_total = PlanificacionDespachosService._calcular_cantidad_total_of(of.id)
                cantidad_despachada = PlanificacionDespachosService._calcular_cantidad_despachada_of(of.id)
                cantidad_disponible = cantidad_total - cantidad_despachada
                
                if cantidad_disponible > 0:
                    ofs_disponibles.append({
                        'id': of.id,
                        'codigo': of.codigo,
                        'descripcion': of.descripcion,
                        'cantidad_total': float(cantidad_total),
                        'cantidad_despachada': float(cantidad_despachada),
                        'cantidad_disponible': float(cantidad_disponible),
                        'estado': of.estado.value,
                        'fecha_entrega_of': of.fecha_entrega_fabrica.isoformat() if of.fecha_entrega_fabrica else None
                    })
            
            return ofs_disponibles
            
        except Exception as e:
            logger.error(f"Error obteniendo OFs disponibles para hito {hito_id}: {str(e)}")
            return []
    
    @staticmethod
    def _calcular_cantidad_total_of(of_id: int) -> float:
        """Calcula la cantidad total de una OF basada en sus items"""
        try:
            from models import OrdenFabricacionItem
            total = db.session.query(func.sum(OrdenFabricacionItem.cantidad)).filter_by(
                of_id=of_id
            ).scalar() or 0
            return float(total)
        except Exception:
            return 0.0
    
    @staticmethod
    def _calcular_cantidad_despachada_of(of_id: int) -> float:
        """Calcula la cantidad ya despachada de una OF"""
        try:
            total = db.session.query(func.sum(DespachoOrdenFabricacion.cantidad_despachada)).filter_by(
                orden_fabricacion_id=of_id
            ).scalar() or 0
            return float(total)
        except Exception:
            return 0.0
    
    @staticmethod
    def get_hitos_proximos_vencimiento(dias: int = 7) -> List[Dict[str, Any]]:
        """
        Obtiene hitos próximos a vencer en los próximos N días
        """
        try:
            fecha_limite = date.today() + timedelta(days=dias)
            
            from models import PlanEntrega, Contrato
            hitos = db.session.query(HitoEntrega).join(
                PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id
            ).join(
                Contrato, PlanEntrega.contrato_id == Contrato.id
            ).join(
                Proyecto, Contrato.proyecto_id == Proyecto.id
            ).join(
                Cliente, Proyecto.cliente_id == Cliente.id
            ).filter(
                HitoEntrega.fecha_programada <= fecha_limite,
                HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
            ).options(
                selectinload(HitoEntrega.plan_entrega).selectinload(PlanEntrega.contrato).selectinload(Contrato.proyecto).selectinload(Proyecto.cliente),
                selectinload(HitoEntrega.despachos)
            ).order_by(
                HitoEntrega.fecha_programada
            ).all()
            
            hitos_proximos = []
            for hito in hitos:
                dias_restantes = (hito.fecha_programada - date.today()).days
                despacho_creado = len(hito.despachos) > 0
                
                hitos_proximos.append({
                    'id': hito.id,
                    'descripcion': hito.descripcion,
                    'fecha_entrega': hito.fecha_programada,
                    'dias_restantes': dias_restantes,
                    'cliente_nombre': hito.plan_entrega.contrato.proyecto.cliente.nombre,
                    'proyecto_nombre': hito.plan_entrega.contrato.proyecto.nombre,
                    'contrato_numero_oc': hito.plan_entrega.contrato.numero_oc,
                    'despacho_creado': despacho_creado,
                    'urgente': dias_restantes <= 2
                })
            
            return hitos_proximos
            
        except Exception as e:
            logger.error(f"Error obteniendo hitos próximos: {str(e)}")
            raise Exception(f"Error obteniendo hitos próximos: {str(e)}")
    
    @staticmethod
    def get_estadisticas_planificacion() -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de la planificación de despachos
        """
        try:
            # Total de hitos pendientes
            total_pendientes = db.session.query(HitoEntrega).filter(
                HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
            ).count()
            
            # Hitos atrasados
            total_atrasados = db.session.query(HitoEntrega).filter(
                HitoEntrega.estado == EstadoHitoEntrega.ATRASADO
            ).count()
            
            # Hitos próximos (7 días)
            fecha_limite = date.today() + timedelta(days=7)
            total_proximos = db.session.query(HitoEntrega).filter(
                HitoEntrega.fecha_programada <= fecha_limite,
                HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
            ).count()
            
            # Despachos programados este mes
            inicio_mes = date.today().replace(day=1)
            despachos_mes = db.session.query(Despacho).filter(
                func.date(Despacho.fecha_programada) >= inicio_mes
            ).count()
            
            # OFs listas para despacho (usando sistema de áreas)
            from models import OrdenAreaProgreso, Area, AreaEstado, TipoArea
            ofs_listas = db.session.query(OrdenFabricacion).join(
                OrdenAreaProgreso, OrdenFabricacion.id == OrdenAreaProgreso.orden_fabricacion_id
            ).join(
                Area, OrdenAreaProgreso.area_id == Area.id
            ).join(
                AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id
            ).filter(
                OrdenAreaProgreso.es_actual == True,
                Area.tipo == TipoArea.BODEGA,
                AreaEstado.codigo == 'listo_para_despacho'
            ).count()
            
            return {
                'total_hitos_pendientes': total_pendientes,
                'total_hitos_atrasados': total_atrasados,
                'total_hitos_proximos': total_proximos,
                'despachos_programados_mes': despachos_mes,
                'ofs_listas_despacho': ofs_listas,
                'fecha_consulta': date.today().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {str(e)}")
            raise Exception(f"Error obteniendo estadísticas: {str(e)}")