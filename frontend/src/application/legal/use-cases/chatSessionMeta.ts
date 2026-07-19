export interface ConversationMetaInput {
  id: string;
  language: string;
  title?: string;
  created_at: string;
  updated_at?: string;
  message_count?: number;
}

export function backendToSessionMeta(conv: ConversationMetaInput) {
  return {
    id: conv.id,
    title: conv.title || 'Conversación',
    preview: '',
    language: conv.language as 'spanish' | 'quechua',
    createdAt: conv.created_at,
    updatedAt: conv.updated_at || conv.created_at,
    messageCount: conv.message_count ?? 0,
  };
}
