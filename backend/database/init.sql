-- Esquema completo para IA Jurídica con Context Engineering
-- PostgreSQL + Redis + Weaviate Integration

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector"; -- Para embeddings

-- Crear esquema principal
CREATE SCHEMA IF NOT EXISTS juridica_schema;
SET search_path TO juridica_schema, public;

-- Tabla de Conversaciones
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    language VARCHAR(10) DEFAULT 'spanish',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true
);

-- Tabla de Mensajes
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    language VARCHAR(10) DEFAULT 'spanish',
    tokens_used INTEGER DEFAULT 0,
    model_used VARCHAR(100),
    embedding vector(1024), -- Cohere embedding dimension
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Tabla de Contexto Cultural (Context Engineering)
CREATE TABLE IF NOT EXISTS cultural_contexts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    culture_code VARCHAR(10) NOT NULL,
    context_type VARCHAR(50) NOT NULL, -- 'legal', 'cultural', 'protocol', 'regional'
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Protocolos Culturales
CREATE TABLE IF NOT EXISTS cultural_protocols (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    context_id UUID NOT NULL REFERENCES cultural_contexts(id) ON DELETE CASCADE,
    protocol_name VARCHAR(255) NOT NULL,
    protocol_type VARCHAR(50) NOT NULL, -- 'greeting', 'formality', 'documentation', 'procedure'
    rules TEXT NOT NULL,
    examples TEXT,
    is_mandatory BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Sesiones de Usuario
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    conversation_id UUID REFERENCES conversations(id),
    context_stack JSONB DEFAULT '[]', -- Stack de contextos activos
    language_preferences JSONB DEFAULT '{}',
    cultural_profile JSONB DEFAULT '{}',
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Documentos Procesados
CREATE TABLE IF NOT EXISTS processed_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    document_type VARCHAR(100), -- 'law', 'regulation', 'contract', 'case'
    jurisdiction VARCHAR(100),
    language VARCHAR(10) DEFAULT 'spanish',
    processing_status VARCHAR(20) DEFAULT 'pending',
    chunk_count INTEGER DEFAULT 0,
    embedding_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Usuarios
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',
    cultural_profile JSONB DEFAULT '{}',
    language_preferences JSONB DEFAULT '{"primary": "spanish", "secondary": "english"}',
    api_key VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices optimizados
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_active ON conversations(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_embedding ON messages USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_cultural_contexts_type ON cultural_contexts(context_type);
CREATE INDEX IF NOT EXISTS idx_cultural_contexts_culture ON cultural_contexts(culture_code);
CREATE INDEX IF NOT EXISTS idx_cultural_contexts_embedding ON cultural_contexts USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_documents_status ON processed_documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_type ON processed_documents(document_type);

-- Triggers para updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cultural_contexts_updated_at BEFORE UPDATE ON cultural_contexts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_processed_documents_updated_at BEFORE UPDATE ON processed_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Datos iniciales de contexto cultural peruano
INSERT INTO cultural_contexts (name, description, culture_code, context_type, content) VALUES
('Formalidad Legal Peruana', 'Nivel de formalidad requerido en documentos legales peruanos', 'PE', 'legal', 
'En el sistema legal peruano, se requiere un alto grado de formalidad en todos los documentos. Los escritos judiciales deben seguir formatos específicos, incluir numeración de fojas, y utilizar lenguaje técnico apropiado.'),
('Tratamiento de Abogados', 'Protocolo para dirigirse a abogados y autoridades legales', 'PE', 'protocol',
'En Perú se utiliza "Doctor/a" para abogados, "Señor/a Juez/a" para jueces, y "Excelencia" para ministros. El trato siempre es formal.'),
('Documentos Esenciales', 'Documentos básicos requeridos en trámites legales peruanos', 'PE', 'legal',
'DNI, poderes, partidas de nacimiento/matrimonio, certificados de domicilio, y comprobantes de pago son documentos esenciales en la mayoría de trámites.'),
('Tiempos Legales', 'Duración típica de procesos legales en Perú', 'PE', 'legal',
'Los procesos civiles pueden durar 1-3 años, procesos laborales 6-12 meses, y procesos constitucionales 3-6 meses. La justicia gratuita puede extender los plazos.')
ON CONFLICT (name) DO NOTHING;

-- Insertar protocolos culturales
INSERT INTO cultural_protocols (context_id, protocol_name, protocol_type, rules, examples) VALUES
((SELECT id FROM cultural_contexts WHERE name = 'Formalidad Legal Peruana'), 'Formato de Escrito', 'documentation', 
'Escritos deben tener: sumilla, petitorio, fundamentos, anexos numerados, firma y sello del abogado.', 
'Demanda civil: Sumilla: "Interpone demanda de obligación de dar suma de dinero"'),
((SELECT id FROM cultural_contexts WHERE name = 'Tratamiento de Abogados'), 'Saludo Formal', 'greeting',
'Siempre usar "Estimado Doctor/a [Apellido]" o "Señor/a Juez/a [Apellido]". Nunca usar nombres de pila.', 
'"Estimado Doctor García:" vs incorrecto "Estimado Carlos:"')
ON CONFLICT DO NOTHING;

-- Crear usuario inicial
INSERT INTO users (email, username, full_name, role) VALUES
('admin@iajuridica.com', 'admin', 'Administrador IA Jurídica', 'admin')
ON CONFLICT (email) DO NOTHING;

-- Confirmación
DO $$
BEGIN
    RAISE NOTICE 'Base de datos IA Jurídica inicializada correctamente';
    RAISE NOTICE 'Tablas creadas: conversations, messages, cultural_contexts, cultural_protocols, user_sessions, processed_documents, users';
    RAISE NOTICE 'Contextos culturales iniciales insertados: %', (SELECT COUNT(*) FROM cultural_contexts);
END $$;
