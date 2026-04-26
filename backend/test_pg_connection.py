#!/usr/bin/env python3
"""
Script de prueba para conexión PostgreSQL
"""

import psycopg
import asyncio

async def test_connection():
    """Probar diferentes métodos de conexión"""
    
    # Configuración
    host = "localhost"
    port = 5432
    dbname = "juridica_db"
    user = "juridica_user"
    password = "juridica_password"
    
    print("🔍 Probando conexión a PostgreSQL...")
    
    # Método 1: Con contraseña
    try:
        print("\n--- Método 1: Con contraseña ---")
        conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=5
        )
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"✅ Conexión exitosa: {version[:50]}...")
        
        conn.close()
        print("✅ Conexión cerrada")
        
    except Exception as e:
        print(f"❌ Método 1 falló: {e}")
    
    # Método 2: Sin contraseña (trust)
    try:
        print("\n--- Método 2: Sin contraseña (trust) ---")
        conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            connect_timeout=5
        )
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"✅ Conexión exitosa: {version[:50]}...")
        
        conn.close()
        print("✅ Conexión cerrada")
        
    except Exception as e:
        print(f"❌ Método 2 falló: {e}")
    
    # Método 3: Usando URL completa
    try:
        print("\n--- Método 3: URL completa ---")
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        conn = psycopg.connect(database_url)
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"✅ Conexión exitosa: {version[:50]}...")
        
        conn.close()
        print("✅ Conexión cerrada")
        
    except Exception as e:
        print(f"❌ Método 3 falló: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
