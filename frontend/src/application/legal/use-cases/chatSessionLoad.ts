import type { ChatSessionMeta } from '../../../domain/legal/types';
import type { ApiResponse, Conversation } from '../services/apiService';

export type SessionLoadResult =
  | { success: true; sessions: ChatSessionMeta[] }
  | { success: false; error: string };

type ListConversations = (
  limit?: number,
  activeOnly?: boolean
) => Promise<ApiResponse<{
  conversations: Conversation[];
  total_count: number;
  active_count: number;
}>>;

type MapConversation = (conversation: Conversation) => ChatSessionMeta;

export async function loadChatSessions(
  listConversations: ListConversations,
  mapConversation: MapConversation
): Promise<SessionLoadResult> {
  try {
    const response = await listConversations(50, true);
    if (response.success && response.data) {
      return {
        success: true,
        sessions: response.data.conversations.map(mapConversation),
      };
    }

    return { success: false, error: response.error ?? 'Unable to load conversations' };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unable to load conversations',
    };
  }
}

export function sessionsAfterLoad(
  currentSessions: ChatSessionMeta[],
  result: SessionLoadResult
): ChatSessionMeta[] {
  return result.success ? result.sessions : currentSessions;
}
