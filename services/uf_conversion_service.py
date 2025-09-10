"""
Servicio para manejo de conversión de Unidad de Fomento (UF) a Pesos Chilenos
Utiliza la API gratuita de mindicador.cl
"""

import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
import logging
from decimal import Decimal
import json
import os

logger = logging.getLogger(__name__)

class UfConversionService:
    """Servicio para obtener valores de UF y realizar conversiones"""
    
    # Cache de valores UF en memoria
    _uf_cache: Dict[str, Dict[str, Any]] = {}
    _cache_expiry_hours = 6  # Cache válido por 6 horas
    
    API_BASE_URL = "https://mindicador.cl/api"
    TIMEOUT = 10  # timeout en segundos para requests
    
    @classmethod
    def get_current_uf_value(cls) -> Optional[Decimal]:
        """
        Obtiene el valor actual de la UF en pesos chilenos
        
        Returns:
            Decimal: Valor actual de UF en CLP, None si hay error
        """
        try:
            # Verificar cache primero
            cache_key = "current_uf"
            cached_data = cls._get_from_cache(cache_key)
            
            if cached_data:
                logger.info(f"UF obtenida desde cache: {cached_data['valor']}")
                return Decimal(str(cached_data['valor']))
            
            # Obtener desde API
            response = requests.get(
                f"{cls.API_BASE_URL}/uf",
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Validar estructura de respuesta - mindicador.cl devuelve formato serie
            if 'serie' not in data or not data['serie']:
                logger.error(f"Estructura de respuesta inválida de mindicador.cl: {data}")
                return None
            
            # Tomar el primer valor (más reciente) de la serie
            uf_value = data['serie'][0]['valor']
            uf_date = data['serie'][0].get('fecha', datetime.now().isoformat())
            
            # Guardar en cache
            cls._save_to_cache(cache_key, {
                'valor': uf_value,
                'fecha': uf_date,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"UF obtenida desde API: {uf_value} CLP")
            return Decimal(str(uf_value))
            
        except requests.exceptions.Timeout:
            logger.error("Timeout al obtener valor UF de mindicador.cl")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión con mindicador.cl: {e}")
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error procesando respuesta de UF: {e}")
        except Exception as e:
            logger.error(f"Error inesperado obteniendo UF: {e}")
            
        return None
    
    @classmethod
    def get_uf_value_for_date(cls, target_date: date) -> Optional[Decimal]:
        """
        Obtiene el valor de UF para una fecha específica
        
        Args:
            target_date: Fecha para la cual obtener el valor UF
            
        Returns:
            Decimal: Valor de UF para la fecha, None si hay error
        """
        try:
            # Verificar cache primero
            date_str = target_date.strftime("%Y-%m-%d")
            cache_key = f"uf_{date_str}"
            cached_data = cls._get_from_cache(cache_key)
            
            if cached_data:
                logger.info(f"UF para {date_str} obtenida desde cache: {cached_data['valor']}")
                return Decimal(str(cached_data['valor']))
            
            # Formatear fecha para API (dd-mm-yyyy)
            api_date = target_date.strftime("%d-%m-%Y")
            
            response = requests.get(
                f"{cls.API_BASE_URL}/uf/{api_date}",
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Validar estructura - para fechas específicas también devuelve formato serie
            if 'serie' not in data or not data['serie']:
                logger.error(f"No se encontró valor UF para fecha {date_str}: {data}")
                return None
            
            # Tomar el primer valor de la serie (debe ser el de la fecha solicitada)
            uf_value = data['serie'][0]['valor']
            
            # Guardar en cache (cache más largo para fechas históricas)
            cls._save_to_cache(cache_key, {
                'valor': uf_value,
                'fecha': date_str,
                'timestamp': datetime.now().isoformat()
            }, expiry_hours=24)  # Cache de 24 horas para fechas históricas
            
            logger.info(f"UF para {date_str} obtenida desde API: {uf_value} CLP")
            return Decimal(str(uf_value))
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo UF para fecha {target_date}: {e}")
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error procesando respuesta UF para fecha {target_date}: {e}")
        except Exception as e:
            logger.error(f"Error inesperado obteniendo UF para fecha {target_date}: {e}")
            
        return None
    
    @classmethod
    def convert_uf_to_clp(cls, uf_amount: Decimal, conversion_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Convierte un monto en UF a Pesos Chilenos
        
        Args:
            uf_amount: Monto en UF a convertir
            conversion_date: Fecha para la conversión (usa hoy si no se especifica)
            
        Returns:
            Dict con información de conversión o None si hay error
        """
        if not uf_amount or uf_amount <= 0:
            logger.warning("Monto UF inválido para conversión")
            return None
        
        # Usar fecha actual si no se especifica
        if not conversion_date:
            conversion_date = date.today()
        
        # Obtener valor UF para la fecha
        if conversion_date == date.today():
            uf_value = cls.get_current_uf_value()
        else:
            uf_value = cls.get_uf_value_for_date(conversion_date)
        
        if not uf_value:
            logger.error(f"No se pudo obtener valor UF para conversión en fecha {conversion_date}")
            return None
        
        # Realizar conversión
        clp_amount = uf_amount * uf_value
        
        result = {
            'uf_amount': uf_amount,
            'uf_value': uf_value,
            'clp_amount': clp_amount,
            'conversion_date': conversion_date,
            'conversion_timestamp': datetime.now()
        }
        
        logger.info(f"Conversión realizada: {uf_amount} UF = {clp_amount} CLP (UF: {uf_value})")
        return result
    
    @classmethod
    def convert_clp_to_uf(cls, clp_amount: Decimal, conversion_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Convierte un monto en Pesos Chilenos a UF
        
        Args:
            clp_amount: Monto en CLP a convertir
            conversion_date: Fecha para la conversión (usa hoy si no se especifica)
            
        Returns:
            Dict con información de conversión o None si hay error
        """
        if not clp_amount or clp_amount <= 0:
            logger.warning("Monto CLP inválido para conversión")
            return None
        
        # Usar fecha actual si no se especifica
        if not conversion_date:
            conversion_date = date.today()
        
        # Obtener valor UF para la fecha
        if conversion_date == date.today():
            uf_value = cls.get_current_uf_value()
        else:
            uf_value = cls.get_uf_value_for_date(conversion_date)
        
        if not uf_value:
            logger.error(f"No se pudo obtener valor UF para conversión en fecha {conversion_date}")
            return None
        
        # Realizar conversión
        uf_amount = clp_amount / uf_value
        
        result = {
            'clp_amount': clp_amount,
            'uf_value': uf_value,
            'uf_amount': uf_amount,
            'conversion_date': conversion_date,
            'conversion_timestamp': datetime.now()
        }
        
        logger.info(f"Conversión realizada: {clp_amount} CLP = {uf_amount} UF (UF: {uf_value})")
        return result
    
    @classmethod
    def get_uf_info(cls) -> Dict[str, Any]:
        """
        Obtiene información completa sobre el estado actual de UF
        
        Returns:
            Dict con información detallada
        """
        current_uf = cls.get_current_uf_value()
        
        # Intentar obtener UF de ayer para comparación
        yesterday = date.today() - timedelta(days=1)
        yesterday_uf = cls.get_uf_value_for_date(yesterday)
        
        info = {
            'current_value': current_uf,
            'date': date.today().isoformat(),
            'timestamp': datetime.now().isoformat(),
            'currency': 'CLP',
            'source': 'mindicador.cl'
        }
        
        # Agregar comparación si tenemos valor de ayer
        if current_uf and yesterday_uf:
            change = current_uf - yesterday_uf
            change_percent = (change / yesterday_uf * 100) if yesterday_uf != 0 else 0
            
            info.update({
                'previous_value': yesterday_uf,
                'change': change,
                'change_percent': change_percent
            })
        
        return info
    
    @classmethod
    def _get_from_cache(cls, key: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos del cache si están vigentes"""
        if key not in cls._uf_cache:
            return None
        
        cached_data = cls._uf_cache[key]
        cached_time = datetime.fromisoformat(cached_data['timestamp'])
        
        # Verificar si el cache ha expirado
        expiry_hours = cached_data.get('expiry_hours', cls._cache_expiry_hours)
        if datetime.now() - cached_time > timedelta(hours=expiry_hours):
            # Cache expirado, eliminarlo
            del cls._uf_cache[key]
            return None
        
        return cached_data
    
    @classmethod
    def _save_to_cache(cls, key: str, data: Dict[str, Any], expiry_hours: Optional[int] = None):
        """Guarda datos en cache"""
        data['expiry_hours'] = expiry_hours or cls._cache_expiry_hours
        cls._uf_cache[key] = data
    
    @classmethod
    def clear_cache(cls):
        """Limpia el cache de UF"""
        cls._uf_cache.clear()
        logger.info("Cache de UF limpiado")
    
    @classmethod
    def get_cache_info(cls) -> Dict[str, Any]:
        """Obtiene información sobre el estado del cache"""
        return {
            'cache_size': len(cls._uf_cache),
            'cache_keys': list(cls._uf_cache.keys()),
            'cache_expiry_hours': cls._cache_expiry_hours
        }

# Función de conveniencia para obtener valor UF actual
def get_current_uf() -> Optional[Decimal]:
    """Función de conveniencia para obtener valor UF actual"""
    return UfConversionService.get_current_uf_value()

# Función de conveniencia para conversión UF a CLP
def convert_uf_to_clp(uf_amount: Decimal, conversion_date: Optional[date] = None) -> Optional[Decimal]:
    """Función de conveniencia para convertir UF a CLP"""
    result = UfConversionService.convert_uf_to_clp(uf_amount, conversion_date)
    return result['clp_amount'] if result else None