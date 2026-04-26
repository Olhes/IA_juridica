"""
Debug para verificar conexión exacta
"""

import asyncio
import psycopg
from config.settings import settings

async def test_connection():
    print("=== DEBUG DE CONEXIÓN ===")
    print(f"settings.DATABASE_USER: '{settings.DATABASE_USER}'")
    print(f"settings.DATABASE_URL: '{settings.DATABASE_URL}'")
    
    try:
        conn = psycopg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            dbname=settings.DATABASE_NAME,
            user=settings.DATABASE_USER,  # ← ESTA ES LA CLAVE
            password=settings.DATABASE_PASSWORD,
            connect_timeout=10,
            client_encoding='UTF8'
        )
        print(f"✅ Conectado con usuario: {settings.DATABASE_USER}")
        conn.close()
    except Exception as e:
        print(f"❌ Error con usuario '{settings.DATABASE_USER}': {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
