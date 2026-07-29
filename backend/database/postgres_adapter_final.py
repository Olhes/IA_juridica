"""
PostgreSQL Adapter Final para IA Jurídica
Conexión simple y robusta
"""

import asyncio
import psycopg
from typing import Dict, Any, Optional, List

from config.settings import settings


class DatabaseUnavailableError(RuntimeError):
    pass


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
                    # En producción usar DATABASE_URL, en desarrollo usar configuración local
                    if settings.ENVIRONMENT == "production" and settings.DATABASE_URL:
                        print(f"  🔧 Usando DATABASE_URL (producción)")
                        try:
                            conn = psycopg.connect(settings.DATABASE_URL, connect_timeout=10)
                            # Configurar search path para usar múltiples schemas
                            with conn.cursor() as cursor:
                                cursor.execute("SET search_path TO conversations_schema, auth_schema, rag_schema, legal_schema, public")
                                conn.commit()
                            print(f"  ✅ Conexión exitosa via DATABASE_URL")
                            return conn
                        except Exception as e:
                            print(f"  Error conectando via DATABASE_URL: {e}")
                            raise
                    else:
                        # Desarrollo local: configuración Docker
                        actual_user = "juridica_user"
                        print(f"  🔧 Usando configuración local: {actual_user} (trust auth)")
                        
                        try:
                            conn = psycopg.connect(
                                host=settings.DATABASE_HOST or "localhost",
                                port=5433,  # Puerto del container Docker (evita conflicto con PostgreSQL local)
                                dbname=settings.DATABASE_NAME or "juridica_db",
                                user=actual_user,
                                password="",
                                connect_timeout=10
                            )
                            # Configurar search path para usar múltiples schemas
                            with conn.cursor() as cursor:
                                cursor.execute("SET search_path TO conversations_schema, auth_schema, rag_schema, legal_schema, public")
                                conn.commit()
                            print(f"  ✅ Conexión exitosa para: {actual_user}")
                            return conn
                        except Exception:
                            print("  PostgreSQL connection failed")
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
                
            except Exception:
                print(f"PostgreSQL connection attempt {attempt + 1} failed")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                else:
                    print("PostgreSQL unavailable; continuing without persistence")
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
        except Exception:
            return {
                'status': 'unhealthy',
                'database': 'postgresql',
                'timestamp': str(asyncio.get_event_loop().time())
            }
    
    def is_connected(self) -> bool:
        """Verificar si la conexión está activa"""
        return self.conn is not None
    
    # ── Métodos para Context Engineering ─────────────────────────────────────
    async def create_conversation(self, user_id: str, title: str = None, language: str = "spanish") -> Dict[str, Any]:
        """Crear una nueva conversación"""
        if not self.conn:
            raise DatabaseUnavailableError("PostgreSQL unavailable")
        
        loop = asyncio.get_event_loop()
        
        def create_sync():
            with self.conn.cursor() as cursor:
                try:
                    # Insertar conversación en conversations_schema
                    cursor.execute("""
                        INSERT INTO conversations_schema.conversations (user_id, title, language)
                        VALUES (%s, %s, %s)
                        RETURNING id, user_id, title, language, created_at
                    """, (user_id, title or f"Conversación en {language}", language))
                    
                    result = cursor.fetchone()
                    self.conn.commit()
                    
                    return {
                        'id': str(result[0]),
                        'user_id': str(result[1]),
                        'title': result[2],
                        'language': result[3],
                        'created_at': result[4].isoformat(),
                        'updated_at': result[4].isoformat(),
                        'metadata': {},
                        'is_active': True
                    }
                except Exception as e:
                    self.conn.rollback()
                    raise e
        
        return await loop.run_in_executor(None, create_sync)
    
    async def get_conversation(self, conversation_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """Obtener una conversación por ID"""
        if not self.conn:
            return None
        
        loop = asyncio.get_event_loop()
        
        def get_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, user_id, title, language, created_at, updated_at, metadata, is_active
                    FROM conversations_schema.conversations
                    WHERE id = %s AND user_id = %s
                """, (conversation_id, owner_id))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                return {
                    'id': str(result[0]),
                    'user_id': str(result[1]),
                    'title': result[2],
                    'language': result[3],
                    'created_at': result[4].isoformat(),
                    'updated_at': result[5].isoformat() if result[5] else result[4].isoformat(),
                    'metadata': result[6] or {},
                    'is_active': result[7],
                }
        
        return await loop.run_in_executor(None, get_sync)
    
    async def create_message(self, conversation_id: str, owner_id: str, content: str, role: str, metadata: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Crear un nuevo mensaje en una conversación"""
        if not self.conn:
            raise Exception("PostgreSQL no conectado")
        
        loop = asyncio.get_event_loop()
        
        def create_sync():
            with self.conn.cursor() as cursor:
                try:
                    # Insertar mensaje en conversations_schema
                    import json
                    from datetime import datetime
                    
                    def serialize_metadata(obj):
                        """Serializa metadata a JSON, manejando datetime y otros objetos no serializables"""
                        if isinstance(obj, datetime):
                            return obj.isoformat()
                        elif isinstance(obj, dict):
                            return {k: serialize_metadata(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [serialize_metadata(item) for item in obj]
                        else:
                            return obj
                    
                    cursor.execute("""
                        INSERT INTO conversations_schema.messages (conversation_id, content, role, metadata)
                        SELECT c.id, %s, %s, %s
                        FROM conversations_schema.conversations c
                        WHERE c.id = %s AND c.user_id = %s
                        RETURNING id, conversation_id, content, role, metadata, created_at
                    """, (
                        content,
                        role,
                        json.dumps(serialize_metadata(metadata or {})),
                        conversation_id,
                        owner_id,
                    ))
                    
                    result = cursor.fetchone()
                    if not result:
                        self.conn.rollback()
                        return None
                    self.conn.commit()
                    
                    return {
                        'id': str(result[0]),
                        'conversation_id': str(result[1]),
                        'content': result[2],
                        'role': result[3],
                        'metadata': result[4] or {},
                        'message_type': 'text',  # Valor por defecto
                        'tokens_used': 0,        # Valor por defecto
                        'model_used': None,      # Valor por defecto
                        'created_at': result[5].isoformat()
                    }
                except Exception as e:
                    self.conn.rollback()
                    raise e
        
        return await loop.run_in_executor(None, create_sync)
    
    async def get_conversation_messages(self, conversation_id: str, owner_id: str) -> List[Dict[str, Any]]:
        """Obtener todos los mensajes de una conversación"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def get_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT m.id, m.conversation_id, m.content, m.role, m.metadata, m.created_at
                    FROM conversations_schema.messages m
                    INNER JOIN conversations_schema.conversations c ON c.id = m.conversation_id
                    WHERE m.conversation_id = %s AND c.user_id = %s
                    ORDER BY m.created_at ASC
                """, (conversation_id, owner_id))
                
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
    
    async def update_cultural_context(self, conversation_id: str, owner_id: str, cultural_context: str, legal_domain: str = None, user_preferences: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
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
                    SELECT c.id, %s, %s, %s
                    FROM conversations_schema.conversations c
                    WHERE c.id = %s AND c.user_id = %s
                    ON CONFLICT (conversation_id)
                    DO UPDATE SET
                        cultural_context = EXCLUDED.cultural_context,
                        legal_domain = EXCLUDED.legal_domain,
                        user_preferences = EXCLUDED.user_preferences,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, conversation_id, cultural_context, legal_domain, user_preferences, updated_at
                """, (cultural_context, legal_domain, user_preferences or {}, conversation_id, owner_id))
                
                result = cursor.fetchone()
                if not result:
                    self.conn.rollback()
                    return None
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
    
    async def list_conversations(self, owner_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Listar conversaciones con paginación"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def list_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, title, language, created_at, updated_at,
                           (SELECT COUNT(*) FROM conversations_schema.messages WHERE conversation_id = conversations_schema.conversations.id) as message_count
                    FROM conversations_schema.conversations
                     WHERE conversations_schema.conversations.user_id = %s
                     ORDER BY updated_at DESC
                     LIMIT %s OFFSET %s
                """, (owner_id, limit, offset))
                
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
    
    async def get_user_conversations(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener conversaciones de un usuario específico"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def get_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, user_id, title, language, created_at, updated_at, metadata, is_active,
                           (SELECT COUNT(*) FROM conversations_schema.messages WHERE conversation_id = conversations_schema.conversations.id) as message_count
                    FROM conversations_schema.conversations
                    WHERE user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, (user_id, limit))
                
                results = cursor.fetchall()
                return [
                    {
                        'id': str(row[0]),
                        'user_id': str(row[1]),
                        'title': row[2],
                        'language': row[3],
                        'created_at': row[4].isoformat(),
                        'updated_at': row[5].isoformat() if row[5] else None,
                        'metadata': row[6] or {},
                        'is_active': row[7],
                        'message_count': row[8] or 0
                    }
                    for row in results
                ]
        
        return await loop.run_in_executor(None, get_sync)
    
    async def update_conversation(self, conversation_id: str, owner_id: str, update_data: Dict[str, Any]) -> bool:
        """Actualizar metadata de conversación"""
        if not self.conn:
            return False
        
        loop = asyncio.get_event_loop()
        
        def update_sync():
            with self.conn.cursor() as cursor:
                # Convertir objeto Pydantic a diccionario y filtrar valores nulos
                update_dict = update_data.model_dump() if hasattr(update_data, 'model_dump') else dict(update_data)
                filtered_data = {k: v for k, v in update_dict.items() if v is not None}
                # Construir consulta dinámica basada en los campos a actualizar
                set_clauses = []
                values = []
                
                if filtered_data.get('title') is not None:
                    set_clauses.append("title = %s")
                    values.append(filtered_data['title'])
                
                if filtered_data.get('metadata') is not None:
                    set_clauses.append("metadata = %s")
                    import json
                    from datetime import datetime
                    
                    def serialize_metadata(obj):
                        """Serializa metadata a JSON, manejando datetime y otros objetos no serializables"""
                        if isinstance(obj, datetime):
                            return obj.isoformat()
                        elif isinstance(obj, dict):
                            return {k: serialize_metadata(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [serialize_metadata(item) for item in obj]
                        else:
                            return obj
                    
                    values.append(json.dumps(serialize_metadata(filtered_data['metadata'])))
                
                if filtered_data.get('is_active') is not None:
                    set_clauses.append("is_active = %s")
                    values.append(filtered_data['is_active'])
                
                if not set_clauses:
                    return False  # Nada que actualizar
                
                # Agregar updated_at
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                
                values.extend((conversation_id, owner_id))
                
                try:
                    sql = f"UPDATE conversations_schema.conversations SET {', '.join(set_clauses)} WHERE id = %s AND user_id = %s RETURNING id"
                    cursor.execute(sql, values)
                    
                    result = cursor.fetchone()
                    self.conn.commit()
                    return result is not None
                except Exception as e:
                    self.conn.rollback()
                    raise e
        
        return await loop.run_in_executor(None, update_sync)
    
    async def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        """Eliminar una conversación"""
        if not self.conn:
            return False
        
        loop = asyncio.get_event_loop()
        
        def delete_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM conversations_schema.conversations
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (conversation_id, owner_id))
                
                result = cursor.fetchone()
                self.conn.commit()
                return result is not None
        
        return await loop.run_in_executor(None, delete_sync)
    
    async def search_conversations(self, user_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Buscar conversaciones por contenido de mensajes"""
        if not self.conn:
            return []
        
        loop = asyncio.get_event_loop()
        
        def search_sync():
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT c.id, c.user_id, c.title, c.language, c.created_at, c.updated_at, c.metadata, c.is_active
                    FROM conversations_schema.conversations c
                    INNER JOIN conversations_schema.messages m ON c.id = m.conversation_id
                    WHERE c.user_id = %s
                    AND (c.title ILIKE %s OR m.content ILIKE %s)
                    ORDER BY c.updated_at DESC
                    LIMIT %s
                """, (user_id, f"%{query}%", f"%{query}%", limit))
                
                results = cursor.fetchall()
                return [
                    {
                        'id': str(row[0]),
                        'user_id': str(row[1]),
                        'title': row[2],
                        'language': row[3],
                        'created_at': row[4].isoformat(),
                        'updated_at': row[5].isoformat() if row[5] else None,
                        'metadata': row[6] or {},
                        'is_active': row[7]
                    }
                    for row in results
                ]
        
        return await loop.run_in_executor(None, search_sync)


# Instancia global del adaptador
postgres_adapter = PostgreSQLAdapter()
