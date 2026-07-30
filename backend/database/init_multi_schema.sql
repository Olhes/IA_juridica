-- Esquema multi-schema para IA Jurídica - Preparado para Microservicios
-- PostgreSQL + Redis + Vector Integration

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector"; -- Para embeddings

-- ========================================
-- CREACIÓN DE SCHEMAS
-- ========================================
CREATE SCHEMA IF NOT EXISTS auth_schema;
CREATE SCHEMA IF NOT EXISTS conversations_schema;
CREATE SCHEMA IF NOT EXISTS rag_schema;
CREATE SCHEMA IF NOT EXISTS legal_schema;

-- ========================================
-- AUTH_SCHEMA - Gestión de Usuarios y Sesiones
-- ========================================

-- Tabla de Usuarios
CREATE TABLE IF NOT EXISTS auth_schema.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin', 'lawyer')),
    cultural_profile JSONB DEFAULT '{}',
    language_preferences JSONB DEFAULT '{"primary": "spanish", "secondary": "english"}',
    api_key VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- CONVERSATIONS_SCHEMA - Chat y Mensajes
-- ========================================

-- Tabla de Conversaciones
CREATE TABLE IF NOT EXISTS conversations_schema.conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth_schema.users(id),
    title VARCHAR(255) NOT NULL,
    language VARCHAR(10) DEFAULT 'spanish',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true
);

-- Tabla de Sesiones de Usuario (depende de conversations_schema.conversations)
CREATE TABLE IF NOT EXISTS auth_schema.user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth_schema.users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    conversation_id UUID REFERENCES conversations_schema.conversations(id),
    context_stack JSONB DEFAULT '[]',
    language_preferences JSONB DEFAULT '{}',
    cultural_profile JSONB DEFAULT '{}',
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Mensajes
CREATE TABLE IF NOT EXISTS conversations_schema.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations_schema.conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    language VARCHAR(10) DEFAULT 'spanish',
    metadata JSONB DEFAULT '{}',
    embedding vector(1024), -- Para búsqueda semántica
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- RAG_SCHEMA - Documentos y Procesamiento
-- ========================================

-- Tabla de Documentos Procesados
CREATE TABLE IF NOT EXISTS rag_schema.processed_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    document_type VARCHAR(100), -- 'law', 'regulation', 'contract', 'case'
    jurisdiction VARCHAR(100),
    language VARCHAR(10) DEFAULT 'spanish',
    processing_status VARCHAR(20) DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    chunk_count INTEGER DEFAULT 0,
    embedding_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Chunks de Documentos
CREATE TABLE IF NOT EXISTS rag_schema.document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES rag_schema.processed_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_type VARCHAR(50) DEFAULT 'text',
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- LEGAL_SCHEMA - Entidades Legales
-- ========================================

-- Tabla de Entidades Legales
CREATE TABLE IF NOT EXISTS legal_schema.legal_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100) NOT NULL, -- 'person', 'organization', 'court', 'law'
    jurisdiction VARCHAR(100),
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Precedentes Legales
CREATE TABLE IF NOT EXISTS legal_schema.legal_precedents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_number VARCHAR(100) NOT NULL,
    court VARCHAR(255) NOT NULL,
    jurisdiction VARCHAR(100),
    decision_date DATE,
    summary TEXT,
    full_text TEXT,
    relevant_laws TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- ÍNDICES OPTIMIZADOS POR SCHEMA
-- ========================================

-- Auth Schema
CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_schema.users(email);
CREATE INDEX IF NOT EXISTS idx_auth_users_active ON auth_schema.users(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_schema.user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active ON auth_schema.user_sessions(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_schema.user_sessions(user_id);

-- Conversations Schema
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations_schema.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_active ON conversations_schema.conversations(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversations_schema.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON conversations_schema.messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_embedding ON conversations_schema.messages USING ivfflat (embedding vector_cosine_ops);

-- RAG Schema
CREATE INDEX IF NOT EXISTS idx_documents_status ON rag_schema.processed_documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_type ON rag_schema.processed_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_jurisdiction ON rag_schema.processed_documents(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON rag_schema.document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON rag_schema.document_chunks USING ivfflat (embedding vector_cosine_ops);

-- Legal Schema
CREATE INDEX IF NOT EXISTS idx_legal_entities_type ON legal_schema.legal_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_legal_entities_jurisdiction ON legal_schema.legal_entities(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_precedents_court ON legal_schema.legal_precedents(court);
CREATE INDEX IF NOT EXISTS idx_precedents_jurisdiction ON legal_schema.legal_precedents(jurisdiction);

-- ========================================
-- TRIGGERS PARA updated_at
-- ========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers a tablas con updated_at
CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations_schema.conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_processed_documents_updated_at BEFORE UPDATE ON rag_schema.processed_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- POLÍTICAS DE SEGURIDAD (RLS - Row Level Security)
-- ========================================

-- Enable RLS en tablas sensibles
ALTER TABLE auth_schema.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_schema.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations_schema.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations_schema.messages ENABLE ROW LEVEL SECURITY;

-- Políticas básicas (pueden expandirse)
CREATE POLICY users_own_data ON auth_schema.users FOR ALL USING (id = current_setting('app.current_user_id')::uuid);
CREATE POLICY sessions_own_data ON auth_schema.user_sessions FOR ALL USING (user_id = current_setting('app.current_user_id')::uuid);
CREATE POLICY conversations_own_data ON conversations_schema.conversations FOR ALL USING (user_id = current_setting('app.current_user_id')::uuid);
CREATE POLICY messages_own_conversations ON conversations_schema.messages FOR ALL USING (
    conversation_id IN (
        SELECT id FROM conversations_schema.conversations 
        WHERE user_id = current_setting('app.current_user_id')::uuid
    )
);

-- ========================================
-- VISTAS ÚTILES
-- ========================================

-- Vista de conversaciones con conteo de mensajes
CREATE OR REPLACE VIEW conversations_schema.conversation_summary AS
SELECT 
    c.id,
    c.title,
    c.language,
    c.created_at,
    c.updated_at,
    COUNT(m.id) as message_count,
    MAX(m.created_at) as last_message_at
FROM conversations_schema.conversations c
LEFT JOIN conversations_schema.messages m ON c.id = m.conversation_id
GROUP BY c.id, c.title, c.language, c.created_at, c.updated_at;

-- Vista de documentos por estado
CREATE OR REPLACE VIEW rag_schema.document_processing_stats AS
SELECT 
    processing_status,
    COUNT(*) as count,
    SUM(chunk_count) as total_chunks,
    SUM(embedding_count) as total_embeddings
FROM rag_schema.processed_documents
GROUP BY processing_status;

-- ========================================
-- DATOS INICIALES
-- ========================================

-- Insertar usuario demo si no existe
INSERT INTO auth_schema.users (id, email, username, full_name, role)
VALUES (
    uuid_generate_v4(),
    'demo@ia-juridica.com',
    'demo-user',
    'Usuario Demo',
    'user'
) ON CONFLICT (email) DO NOTHING;

-- Reporte de creación
DO $$
BEGIN
    RAISE NOTICE 'Base de datos multi-schema IA Jurídica inicializada correctamente';
    RAISE NOTICE 'Schemas creados: auth_schema, conversations_schema, rag_schema, legal_schema';
    RAISE NOTICE 'Tablas creadas: %', (
        SELECT COUNT(*)
        FROM information_schema.tables 
        WHERE table_schema IN ('auth_schema', 'conversations_schema', 'rag_schema', 'legal_schema')
        AND table_type = 'BASE TABLE'
    );
    RAISE NOTICE 'Usuario demo insertado en auth_schema.users';
END $$;
