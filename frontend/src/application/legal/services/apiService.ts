/**
 * Servicio API para comunicación con el backend de IA Jurídica
 * Maneja persistencia de conversaciones en PostgreSQL
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface Conversation {
  id: string;
  language: string;
  title?: string;
  created_at: string;
  updated_at?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  content: string;
  role: 'user' | 'assistant';
  metadata?: Record<string, any>;
  created_at: string;
}

export interface CulturalContext {
  id: string;
  conversation_id: string;
  cultural_context: string;
  legal_domain?: string;
  user_preferences?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  // ── Conversaciones ────────────────────────────────────────────────
  async createConversation(language: string, title?: string, userId?: string): Promise<ApiResponse<Conversation>> {
    return this.request<Conversation>('/chat/conversations', {
      method: 'POST',
      body: JSON.stringify({ 
        user_id: userId || 'd1d0e0f7-1b3d-43fc-875d-b6991e6c94af',
        language, 
        title 
      }),
    });
  }

  async getConversation(conversationId: string): Promise<ApiResponse<{
    conversation: Conversation;
    messages: Message[];
    total_messages: number;
    context_summary?: any;
  }>> {
    return this.request(`/chat/conversations/${conversationId}`);
  }

  async listConversations(limit = 50, activeOnly = true): Promise<ApiResponse<{
    conversations: Conversation[];
    total_count: number;
    active_count: number;
  }>> {
    return this.request(`/chat/conversations?limit=${limit}&active_only=${activeOnly}`);
  }

  async updateConversation(conversationId: string, updates: {
    title?: string;
    metadata?: Record<string, any>;
    is_active?: boolean;
  }): Promise<ApiResponse<Conversation>> {
    return this.request<Conversation>(`/chat/conversations/${conversationId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteConversation(conversationId: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return this.request(`/chat/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  async searchConversations(query: string, limit = 20): Promise<ApiResponse<{
    results: Conversation[];
    total_count: number;
  }>> {
    return this.request(`/chat/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  }

  async getConversationStats(conversationId: string): Promise<ApiResponse<{
    stats: {
      conversation_id: string;
      message_count: number;
      user_messages: number;
      assistant_messages: number;
      total_tokens: number;
      languages: string[];
      duration_hours: number;
      last_activity: string;
    };
  }>> {
    return this.request(`/chat/conversations/${conversationId}/stats`);
  }

  // ── Chat Message (nuevo endpoint) ─────────────────────────────────────
  async sendChatMessage(
    message: string,
    conversationId?: string,
    language: string = 'spanish',
    sessionToken?: string,
    context?: Record<string, any>
  ): Promise<ApiResponse<{
    success: boolean;
    conversation_id: string;
    session_id: string;
    message: Message;
    conversation_history: Message[];
    metadata: Record<string, any>;
  }>> {
    return this.request('/chat/message', {
      method: 'POST',
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        language,
        session_token: sessionToken,
        context,
      }),
    });
  }

  async continueConversation(
    conversationId: string,
    message: string
  ): Promise<ApiResponse<any>> {
    return this.request(`/chat/conversations/${conversationId}/continue`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  }

  // ── Mensajes (legacy) ─────────────────────────────────────────────────
  async createMessage(
    conversationId: string,
    content: string,
    role: 'user' | 'assistant',
    metadata?: Record<string, any>
  ): Promise<ApiResponse<Message>> {
    return this.request<Message>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: conversationId,
        content,
        role,
        metadata,
      }),
    });
  }

  // ── Contexto Cultural ───────────────────────────────────────────────────────
  async updateContext(
    conversationId: string,
    culturalContext: string,
    legalDomain?: string,
    userPreferences?: Record<string, any>
  ): Promise<ApiResponse<CulturalContext>> {
    return this.request<CulturalContext>(`/conversations/${conversationId}/context`, {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: conversationId,
        cultural_context: culturalContext,
        legal_domain: legalDomain,
        user_preferences: userPreferences,
      }),
    });
  }

  // ── Health Check ───────────────────────────────────────────────────────────
  async healthCheck(): Promise<ApiResponse<any>> {
    return this.request('/health');
  }

  async chatHealthCheck(): Promise<ApiResponse<{
    status: string;
    components: {
      redis: string;
      postgresql: string;
      cache: string;
    };
    timestamp: string;
  }>> {
    return this.request('/chat/health');
  }

  async getSessionInfo(sessionId: string): Promise<ApiResponse<{
    success: boolean;
    session: {
      session_id: string;
      user_id: string;
      conversation_id?: string;
      language_preferences: Record<string, string>;
      cultural_profile: Record<string, any>;
      last_activity: string;
      expires_at: string;
      is_active: boolean;
    };
  }>> {
    return this.request(`/chat/sessions/${sessionId}`);
  }

  async clearSession(sessionToken?: string): Promise<ApiResponse<{
    success: boolean;
    message: string;
  }>> {
    const url = sessionToken ? `/chat/clear-session?session_token=${encodeURIComponent(sessionToken)}` : '/chat/clear-session';
    return this.request(url, {
      method: 'POST',
    });
  }

  async invalidateConversationCache(conversationId: string): Promise<ApiResponse<{
    success: boolean;
    message: string;
  }>> {
    return this.request(`/chat/invalidate-cache/${conversationId}`, {
      method: 'POST',
    });
  }

  // ── Legal Query (existente) ───────────────────────────────────────────────
  async legalQuery(query: string, language: string): Promise<ApiResponse<any>> {
    return this.request('/legal-query', {
      method: 'POST',
      body: JSON.stringify({ query, language }),
    });
  }
}

// Exportar instancia singleton
export const apiService = new ApiService();

// Exportar tipos para uso en componentes
export type { 
  Conversation as BackendConversation, 
  Message as BackendMessage, 
  CulturalContext as BackendCulturalContext, 
  ApiResponse as BackendApiResponse 
};
