from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy import func, and_, or_, desc
from app import db
from models import (
    MovimientoFinanciero, TipoMovimiento, EstadoMovimiento,
    CuentaBancaria, CentroCosto, Proyecto, Contrato
)
import logging

logger = logging.getLogger(__name__)

class TesoreriaService:
    """Servicio para gestión de tesorería y flujo de caja"""
    
    def get_cuentas_bancarias(self, solo_activas: bool = True) -> List[CuentaBancaria]:
        """Obtiene las cuentas bancarias"""
        try:
            query = CuentaBancaria.query
            if solo_activas:
                query = query.filter_by(activa=True)
            return query.order_by(CuentaBancaria.nombre).all()
        except Exception as e:
            logger.error(f"Error obteniendo cuentas bancarias: {str(e)}")
            return []
    
    def get_movimientos_recientes(self, limit: int = 50) -> List[Dict]:
        """Obtiene los movimientos financieros más recientes"""
        try:
            movimientos = MovimientoFinanciero.query.order_by(
                desc(MovimientoFinanciero.fecha),
                desc(MovimientoFinanciero.created_at)
            ).limit(limit).all()
            
            resultado = []
            for mov in movimientos:
                resultado.append({
                    'id': mov.id,
                    'fecha': mov.fecha.isoformat() if mov.fecha else None,
                    'tipo': mov.tipo.value,
                    'monto': float(mov.monto),
                    'descripcion': mov.descripcion,
                    'referencia': mov.referencia,
                    'cuenta': mov.cuenta_bancaria.nombre if mov.cuenta_bancaria else 'Sin cuenta',
                    'proyecto': mov.proyecto.nombre if mov.proyecto else None,
                    'centro_costo': mov.centro_costo.nombre if mov.centro_costo else None,
                    'estado': mov.estado.value,
                    'tipo_class': 'text-success' if mov.tipo == TipoMovimiento.INGRESO else 'text-danger'
                })
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo movimientos recientes: {str(e)}")
            return []
    
    def get_saldo_total(self) -> Dict:
        """Obtiene el saldo total de todas las cuentas"""
        try:
            cuentas = CuentaBancaria.query.filter_by(activa=True).all()
            
            saldo_total = Decimal(0)
            saldos_por_cuenta = []
            
            for cuenta in cuentas:
                saldo = cuenta.saldo_actual or Decimal(0)
                saldo_total += saldo
                
                saldos_por_cuenta.append({
                    'id': cuenta.id,
                    'nombre': cuenta.nombre,
                    'banco': cuenta.banco,
                    'numero': cuenta.numero_cuenta,
                    'saldo': float(saldo),
                    'moneda': cuenta.moneda
                })
            
            return {
                'total': float(saldo_total),
                'cuentas': saldos_por_cuenta
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo saldo total: {str(e)}")
            return {'total': 0, 'cuentas': []}
    
    def crear_movimiento(self, data: Dict) -> MovimientoFinanciero:
        """Crea un nuevo movimiento financiero"""
        try:
            movimiento = MovimientoFinanciero(
                fecha=data['fecha'],
                tipo=TipoMovimiento[data['tipo']],
                monto=data['monto'],
                descripcion=data['descripcion'],
                referencia=data.get('referencia'),
                cuenta_bancaria_id=data.get('cuenta_bancaria_id'),
                centro_costo_id=data.get('centro_costo_id'),
                proyecto_id=data.get('proyecto_id'),
                contrato_id=data.get('contrato_id'),
                estado=EstadoMovimiento.CONFIRMADO,
                fecha_confirmacion=datetime.utcnow(),
                created_by=data.get('created_by')
            )
            
            db.session.add(movimiento)
            
            # Actualizar saldo de cuenta bancaria si aplica
            if movimiento.cuenta_bancaria_id:
                cuenta = CuentaBancaria.query.get(movimiento.cuenta_bancaria_id)
                if cuenta:
                    if movimiento.tipo == TipoMovimiento.INGRESO:
                        cuenta.saldo_actual = (cuenta.saldo_actual or Decimal(0)) + movimiento.monto
                    elif movimiento.tipo == TipoMovimiento.EGRESO:
                        cuenta.saldo_actual = (cuenta.saldo_actual or Decimal(0)) - movimiento.monto
            
            db.session.commit()
            
            logger.info(f"Movimiento financiero creado: {movimiento.id}")
            return movimiento
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando movimiento: {str(e)}")
            raise
    
    def get_flujo_caja_mensual(self) -> Dict:
        """Obtiene el flujo de caja del mes actual"""
        try:
            today = date.today()
            start_of_month = date(today.year, today.month, 1)
            
            return self.get_flujo_caja_periodo(start_of_month, today)
            
        except Exception as e:
            logger.error(f"Error obteniendo flujo de caja mensual: {str(e)}")
            return self._empty_flujo_caja()
    
    def get_flujo_caja_mes(self, year: int, month: int) -> Dict:
        """Obtiene el flujo de caja de un mes específico"""
        try:
            start_date = date(year, month, 1)
            
            # Calcular último día del mes
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
            
            return self.get_flujo_caja_periodo(start_date, end_date)
            
        except Exception as e:
            logger.error(f"Error obteniendo flujo de caja del mes {year}-{month}: {str(e)}")
            return self._empty_flujo_caja()
    
    def get_flujo_caja_periodo(self, fecha_inicio: date, fecha_fin: date) -> Dict:
        """Obtiene el flujo de caja de un período específico"""
        try:
            # Calcular saldo inicial (suma de movimientos anteriores al período)
            saldo_inicial = db.session.query(
                func.coalesce(
                    func.sum(
                        func.case(
                            (MovimientoFinanciero.tipo == TipoMovimiento.INGRESO, MovimientoFinanciero.monto),
                            (MovimientoFinanciero.tipo == TipoMovimiento.EGRESO, -MovimientoFinanciero.monto),
                            else_=0
                        )
                    ),
                    0
                )
            ).filter(
                MovimientoFinanciero.fecha < fecha_inicio,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO
            ).scalar() or Decimal(0)
            
            # Ingresos del período
            ingresos = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.tipo == TipoMovimiento.INGRESO,
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO
            ).scalar() or Decimal(0)
            
            # Egresos del período
            egresos = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.tipo == TipoMovimiento.EGRESO,
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO
            ).scalar() or Decimal(0)
            
            # Movimientos del período
            movimientos = MovimientoFinanciero.query.filter(
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO
            ).order_by(
                MovimientoFinanciero.fecha,
                MovimientoFinanciero.created_at
            ).all()
            
            # Preparar lista de movimientos con saldo acumulado
            movimientos_lista = []
            saldo_acumulado = saldo_inicial
            
            for mov in movimientos:
                if mov.tipo == TipoMovimiento.INGRESO:
                    saldo_acumulado += mov.monto
                elif mov.tipo == TipoMovimiento.EGRESO:
                    saldo_acumulado -= mov.monto
                
                movimientos_lista.append({
                    'fecha': mov.fecha.isoformat(),
                    'tipo': mov.tipo.value,
                    'descripcion': mov.descripcion,
                    'referencia': mov.referencia,
                    'proyecto': mov.proyecto.nombre if mov.proyecto else None,
                    'monto': float(mov.monto),
                    'saldo_acumulado': float(saldo_acumulado)
                })
            
            # Saldo final
            saldo_final = saldo_inicial + ingresos - egresos
            
            # Agrupar por categorías
            categorias_ingresos = self._agrupar_por_categoria(fecha_inicio, fecha_fin, TipoMovimiento.INGRESO)
            categorias_egresos = self._agrupar_por_categoria(fecha_inicio, fecha_fin, TipoMovimiento.EGRESO)
            
            return {
                'fecha_inicio': fecha_inicio.isoformat(),
                'fecha_fin': fecha_fin.isoformat(),
                'saldo_inicial': float(saldo_inicial),
                'total_ingresos': float(ingresos),
                'total_egresos': float(egresos),
                'saldo_final': float(saldo_final),
                'movimientos': movimientos_lista,
                'categorias_ingresos': categorias_ingresos,
                'categorias_egresos': categorias_egresos
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo flujo de caja del período: {str(e)}")
            return self._empty_flujo_caja()
    
    def crear_cuenta_bancaria(self, data: Dict) -> CuentaBancaria:
        """Crea una nueva cuenta bancaria"""
        try:
            cuenta = CuentaBancaria(
                nombre=data['nombre'],
                numero_cuenta=data.get('numero_cuenta'),
                banco=data.get('banco'),
                tipo_cuenta=data.get('tipo_cuenta'),
                saldo_actual=data.get('saldo_inicial', Decimal(0)),
                moneda=data.get('moneda', 'CLP'),
                activa=True,
                created_by=data.get('created_by')
            )
            
            db.session.add(cuenta)
            db.session.commit()
            
            logger.info(f"Cuenta bancaria creada: {cuenta.id}")
            return cuenta
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando cuenta bancaria: {str(e)}")
            raise
    
    def actualizar_saldo_cuenta(self, cuenta_id: int, nuevo_saldo: Decimal) -> bool:
        """Actualiza el saldo de una cuenta bancaria"""
        try:
            cuenta = CuentaBancaria.query.get(cuenta_id)
            if not cuenta:
                raise ValueError(f"Cuenta bancaria {cuenta_id} no encontrada")
            
            cuenta.saldo_actual = nuevo_saldo
            cuenta.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            logger.info(f"Saldo actualizado para cuenta {cuenta_id}: {nuevo_saldo}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando saldo de cuenta: {str(e)}")
            return False
    
    # Métodos auxiliares privados
    def _agrupar_por_categoria(self, fecha_inicio: date, fecha_fin: date, tipo: TipoMovimiento) -> List[Dict]:
        """Agrupa movimientos por categoría (proyecto/centro de costo)"""
        try:
            # Agrupar por proyecto
            por_proyecto = db.session.query(
                Proyecto.nombre,
                func.sum(MovimientoFinanciero.monto).label('total')
            ).join(
                MovimientoFinanciero
            ).filter(
                MovimientoFinanciero.tipo == tipo,
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO,
                MovimientoFinanciero.proyecto_id.isnot(None)
            ).group_by(Proyecto.nombre).all()
            
            # Agrupar por centro de costo
            por_centro = db.session.query(
                CentroCosto.nombre,
                func.sum(MovimientoFinanciero.monto).label('total')
            ).join(
                MovimientoFinanciero
            ).filter(
                MovimientoFinanciero.tipo == tipo,
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO,
                MovimientoFinanciero.centro_costo_id.isnot(None)
            ).group_by(CentroCosto.nombre).all()
            
            # Sin categoría
            sin_categoria = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.tipo == tipo,
                MovimientoFinanciero.fecha >= fecha_inicio,
                MovimientoFinanciero.fecha <= fecha_fin,
                MovimientoFinanciero.estado != EstadoMovimiento.CANCELADO,
                MovimientoFinanciero.proyecto_id.is_(None),
                MovimientoFinanciero.centro_costo_id.is_(None)
            ).scalar() or Decimal(0)
            
            categorias = []
            
            # Agregar proyectos
            for nombre, total in por_proyecto:
                categorias.append({
                    'categoria': f"Proyecto: {nombre}",
                    'total': float(total)
                })
            
            # Agregar centros de costo
            for nombre, total in por_centro:
                categorias.append({
                    'categoria': f"Centro: {nombre}",
                    'total': float(total)
                })
            
            # Agregar sin categoría si existe
            if sin_categoria > 0:
                categorias.append({
                    'categoria': 'Sin categoría',
                    'total': float(sin_categoria)
                })
            
            # Ordenar por total descendente
            categorias.sort(key=lambda x: x['total'], reverse=True)
            
            return categorias
            
        except Exception as e:
            logger.error(f"Error agrupando por categoría: {str(e)}")
            return []
    
    def _empty_flujo_caja(self) -> Dict:
        """Retorna un diccionario vacío de flujo de caja"""
        return {
            'fecha_inicio': None,
            'fecha_fin': None,
            'saldo_inicial': 0,
            'total_ingresos': 0,
            'total_egresos': 0,
            'saldo_final': 0,
            'movimientos': [],
            'categorias_ingresos': [],
            'categorias_egresos': []
        }