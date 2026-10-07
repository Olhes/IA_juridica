"""
Debug para verificar conexión exacta
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import asyncio
import psycopg
from config.settings import settings

async def test_connection():
    print("=== DEBUG DE CONEXIÓN ===")
    print(f"settings.DATABASE_USER: '{settings.DATABASE_USER}'")
    print(f"Destino: {settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}")
    
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
        print(f"❌ Falló la conexión: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_connection())
