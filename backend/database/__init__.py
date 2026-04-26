"""
Inicialización de Base de Datos para IA Jurídica
PostgreSQL + Redis + Weaviate Integration
"""

import asyncio
from typing import Dict, Any, Optional

from .postgres_adapter_final import postgres_adapter
from .redis_adapter import redis_adapter
from config.settings import settings


async def initialize_database():
    """Inicializar todas las conexiones a base de datos"""
    try:
        print("🚀 Inicializando sistema de base de datos...")
        
        # Inicializar PostgreSQL (sin fallar si hay error)
        await postgres_adapter.initialize()
        
        # Inicializar Redis
        await redis_adapter.initialize()
        print("✅ Redis conectado")
        
        # Verificar salud de las conexiones
        pg_health = await postgres_adapter.health_check()
        redis_health = await redis_adapter.health_check()
        
        print(f"🎉 Base de datos inicializada:")
        print(f"   PostgreSQL: {pg_health['status']} ({pg_health.get('version', 'unknown')})")
        print(f"   Redis: {redis_health['status']} (v{redis_health.get('version', 'unknown')})")
        
        return True
        
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        raise


async def close_database():
    """Cerrar todas las conexiones a base de datos"""
    try:
        print("🔄 Cerrando conexiones a base de datos...")
        
        await postgres_adapter.close()
        await redis_adapter.close()
        
        print("✅ Conexiones cerradas")
        
    except Exception as e:
        print(f"❌ Error cerrando base de datos: {e}")


async def health_check() -> Dict[str, Any]:
    """Verificar salud de todas las bases de datos"""
    try:
        pg_health = await postgres_adapter.health_check()
        redis_health = await redis_adapter.health_check()
        
        overall_status = 'healthy' if (
            pg_health['status'] == 'healthy' and 
            redis_health['status'] == 'healthy'
        ) else 'partial' if redis_health['status'] == 'healthy' else 'unhealthy'
        
        return {
            'overall_status': overall_status,
            'postgresql': pg_health,
            'redis': redis_health,
            'timestamp': pg_health['timestamp']
        }
        
    except Exception as e:
        return {
            'overall_status': 'unhealthy',
            'error': str(e),
            'timestamp': str(asyncio.get_event_loop().time())
        }


def get_postgres_adapter():
    """Retorna el adaptador PostgreSQL si está inicializado y conectado"""
    if postgres_adapter.is_connected():
        return postgres_adapter
    return None


# Exportar adaptadores
__all__ = [
    'initialize_database',
    'close_database', 
    'health_check',
    'postgres_adapter',
    'redis_adapter',
    'get_postgres_adapter'
]
