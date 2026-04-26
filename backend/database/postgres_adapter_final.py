"""
PostgreSQL Adapter Final para IA Jurídica
Conexión simple y robusta
"""

import asyncio
import psycopg
import importlib
import sys
from typing import Dict, Any, Optional, List

# Forzar recarga del módulo settings
if 'config.settings' in sys.modules:
    importlib.reload(sys.modules['config.settings'])

from config.settings import settings


class PostgreSQLAdapter:
    """Adaptador PostgreSQL simple y robusto"""
    
    def __init__(self):
        self.conn = None
    
    async def initialize(self):
        """Inicializar conexión PostgreSQL"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🔍 Conectando a PostgreSQL (intento {attempt + 1}/{max_retries})...")
                
                # Pequeño retraso para asegurar que PostgreSQL esté listo
                await asyncio.sleep(1)
                
                # Usar conexión simple
                loop = asyncio.get_event_loop()
                
                def connect_sync():
                    # Usar juridica_user con trust auth (sin contraseña)
                    actual_user = "juridica_user"
                    
                    print(f"  🔧 Usando usuario: {actual_user} (trust auth)")
                    
                    try:
                        conn = psycopg.connect(
                            host=settings.DATABASE_HOST or "localhost",
                            port=5433,  # Puerto del container Docker (evita conflicto con PostgreSQL local)
                            dbname=settings.DATABASE_NAME or "juridica_db",
                            user=actual_user,
                            password="",
                            connect_timeout=10
                        )
                        print(f"  ✅ Conexión exitosa para: {actual_user}")
                        return conn
                    except Exception as e:
                        print(f"  ❌ Falló conexión: {e}")
                        raise
                
                self.conn = await loop.run_in_executor(None, connect_sync)
                
                # Probar conexión simple
                def test_sync():
                    with self.conn.cursor() as cursor:
                        cursor.execute("SELECT version()")
                        version = cursor.fetchone()[0]
                        return version
                
                version = await loop.run_in_executor(None, test_sync)
                print(f"✅ PostgreSQL conectado: {version[:50]}...")
                print("✅ Conexión PostgreSQL inicializada")
                return
                
            except Exception as e:
                print(f"❌ Intento {attempt + 1} fallido: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                else:
                    print(f"❌ Error inicializando PostgreSQL: {e}")
                    print("⚠️ Continuando sin PostgreSQL...")
                    return
    
    async def close(self):
        """Cerrar conexión"""
        if self.conn:
            loop = asyncio.get_event_loop()
            
            def close_sync():
                self.conn.close()
            
            await loop.run_in_executor(None, close_sync)
            print("✅ Conexión PostgreSQL cerrada")
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud de PostgreSQL"""
        if not self.conn:
            return {
                'status': 'unhealthy',
                'database': 'postgresql',
                'error': 'Conexión no inicializada',
                'timestamp': str(asyncio.get_event_loop().time())
            }
        
        try:
            loop = asyncio.get_event_loop()
            
            def test_sync():
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT version()")
                    version = cursor.fetchone()[0]
                    return version
            
            version = await loop.run_in_executor(None, test_sync)
            return {
                'status': 'healthy',
                'database': 'postgresql',
                'version': version,
                'timestamp': str(asyncio.get_event_loop().time())
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'database': 'postgresql',
                'error': str(e),
                'timestamp': str(asyncio.get_event_loop().time())
            }
    
    def is_connected(self) -> bool:
        """Verificar si la conexión está activa"""
        return self.conn is not None
    
    # ── Métodos para Context Engineering ─────────────────────────────────────
    async def create_conversation(self, language: str, title: str = None) -> Dict[str, Any]:
        """Crear una nueva conversación"""
        if not self.conn:
            raise Exception("PostgreSQL no conectado")
        
        loop = asyncio.get_event_loop()
        
        def create_sync():
            with self.conn.cursor() as cursor:
                # Crear tabla si no existe (con la estructura correcta)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID DEFAULT gen_random_uuid(),
                        title VARCHAR(255) NOT NULL,
                        language VARCHAR(10) DEFAULT 'spanish',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB DEFAULT '{}',
                        is_active BOOLEAN DEFAULT true
                    )
                """)
                
                # Insertar conversación
                cursor.execute("""
                    INSERT INTO conversations (title, language)
                    VALUES (%s, %s)
                    RETURNING id, title, language, created_at
                """, (title or f"Conversación en {language}", language))
                
                result = cursor.fetchone()
                self.conn.commit()
                
                return {
                    'id': str(result[0]),
                    'title': result[1],
                    'language': result[2],
                    'created_at': result[3].isoformat()
                }
        
        return await loop.run_in_executor(None, create_sync)
    
    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Obtener una conversación por ID"""
        if not self.conn:
            return None
        
        loop = asyncio.get_event_loop()
        
        def get_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, title, language, created_at, updated_at
                    FROM conversations
                    WHERE id = %s
                """, (conversation_id,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'id': str(result[0]),
                    'title': result[1],
                    'language': result[2],
                    'created_at': result[3].isoformat(),
                    'updated_at': result[4].isoformat() if result[4] else None
                }
        
        return await loop.run_in_executor(None, get_sync)
    
    async def create_message(self, conversation_id: str, content: str, role: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crear un nuevo mensaje en una conversación"""
        if not self.conn:
            raise Exception("PostgreSQL no conectado")
        
        loop = asyncio.get_event_loop()
        
        def create_sync():
            with self.conn.cursor() as cursor:
                # Crear tabla si no existe (con estructura completa)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                        content TEXT NOT NULL,
                        language VARCHAR(10) DEFAULT 'spanish',
                        tokens_used INTEGER DEFAULT 0,
                        model_used VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB DEFAULT '{}'
                    )
                """)
                
                # Insertar mensaje
                cursor.execute("""
                    INSERT INTO messages (conversation_id, content, role, metadata)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, conversation_id, content, role, metadata, created_at
                """, (conversation_id, content, role, metadata or {}))
                
                result = cursor.fetchone()
                self.conn.commit()
                
                return {
                    'id': str(result[0]),
                    'conversation_id': str(result[1]),
                    'content': result[2],
                    'role': result[3],
                    'metadata': result[4] or {},
                    'created_at': result[5].isoformat()
                }
        
        return await loop.run_in_executor(None, create_sync)
    
    async def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Obtener todos los mensajes de una conversación"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def get_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, conversation_id, content, role, metadata, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY created_at ASC
                """, (conversation_id,))
                
                results = cursor.fetchall()
                return [
                    {
                        'id': str(row[0]),
                        'conversation_id': str(row[1]),
                        'content': row[2],
                        'role': row[3],
                        'metadata': row[4] or {},
                        'created_at': row[5].isoformat()
                    }
                    for row in results
                ]
        
        return await loop.run_in_executor(None, get_sync)
    
    async def update_cultural_context(self, conversation_id: str, cultural_context: str, legal_domain: str = None, user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Actualizar o crear contexto cultural de una conversación"""
        if not self.conn:
            raise Exception("PostgreSQL no conectado")
        
        loop = asyncio.get_event_loop()
        
        def update_sync():
            with self.conn.cursor() as cursor:
                # Crear tabla si no existe
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cultural_contexts (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        conversation_id UUID NOT NULL REFERENCES conversations(id) UNIQUE,
                        cultural_context TEXT NOT NULL,
                        legal_domain VARCHAR(100),
                        user_preferences JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Upsert del contexto
                cursor.execute("""
                    INSERT INTO cultural_contexts (conversation_id, cultural_context, legal_domain, user_preferences)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (conversation_id)
                    DO UPDATE SET
                        cultural_context = EXCLUDED.cultural_context,
                        legal_domain = EXCLUDED.legal_domain,
                        user_preferences = EXCLUDED.user_preferences,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, conversation_id, cultural_context, legal_domain, user_preferences, updated_at
                """, (conversation_id, cultural_context, legal_domain, user_preferences or {}))
                
                result = cursor.fetchone()
                self.conn.commit()
                
                return {
                    'id': str(result[0]),
                    'conversation_id': str(result[1]),
                    'cultural_context': result[2],
                    'legal_domain': result[3],
                    'user_preferences': result[4] or {},
                    'updated_at': result[5].isoformat()
                }
        
        return await loop.run_in_executor(None, update_sync)
    
    async def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Listar conversaciones con paginación"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def list_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, title, language, created_at, updated_at,
                           (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as message_count
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                results = cursor.fetchall()
                return [
                    {
                        'id': str(row[0]),
                        'title': row[1],
                        'language': row[2],
                        'created_at': row[3].isoformat(),
                        'updated_at': row[4].isoformat() if row[4] else None,
                        'message_count': row[5] or 0
                    }
                    for row in results
                ]
        
        return await loop.run_in_executor(None, list_sync)


# Instancia global del adaptador
postgres_adapter = PostgreSQLAdapter()
