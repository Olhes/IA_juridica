"""
Script de prueba para conexiones PostgreSQL y Redis
"""

import asyncio
import asyncpg
import redis.asyncio as redis
from config.settings import settings

async def test_postgres():
    """Probar conexión PostgreSQL"""
    print("🔍 Probando conexión PostgreSQL...")
    try:
        # Intentar diferentes hosts
        hosts = ['localhost', '127.0.0.1', 'host.docker.internal']
        
        for host in hosts:
            try:
                print(f"  📍 Intentando host: {host}")
                conn = await asyncpg.connect(
                    host=host,
                    port=settings.DATABASE_PORT,
                    database=settings.DATABASE_NAME,
                    user=settings.DATABASE_USER,
                    password=settings.DATABASE_PASSWORD,
                    command_timeout=5
                )
                result = await conn.fetchval('SELECT version()')
                print(f"  ✅ {host}: {result[:50]}...")
                await conn.close()
                return host
            except Exception as e:
                print(f"  ❌ {host}: {e}")
        
        return None
    except Exception as e:
        print(f"❌ Error general PostgreSQL: {e}")
        return None

async def test_redis():
    """Probar conexión Redis"""
    print("🔍 Probando conexión Redis...")
    try:
        hosts = ['localhost', '127.0.0.1', 'host.docker.internal']
        
        for host in hosts:
            try:
                print(f"  📍 Intentando host: {host}")
                client = redis.from_url(f"redis://{host}:6379")
                await client.ping()
                info = await client.info()
                print(f"  ✅ {host}: Redis v{info.get('redis_version', 'unknown')}")
                await client.close()
                return host
            except Exception as e:
                print(f"  ❌ {host}: {e}")
        
        return None
    except Exception as e:
        print(f"❌ Error general Redis: {e}")
        return None

async def main():
    print("🚀 Iniciando pruebas de conexión...")
    
    pg_host = await test_postgres()
    redis_host = await test_redis()
    
    print(f"\n📋 Resultados:")
    print(f"  PostgreSQL: {pg_host or '❌ No funcionó'}")
    print(f"  Redis: {redis_host or '❌ No funcionó'}")
    
    if pg_host and redis_host:
        print("\n✅ Ambas conexiones funcionaron!")
        print(f"   Usa estos hosts en settings.py:")
        print(f"   DATABASE_HOST: '{pg_host}'")
        print(f"   REDIS_HOST: '{redis_host}'")

if __name__ == "__main__":
    asyncio.run(main())
