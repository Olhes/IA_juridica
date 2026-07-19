import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  loadChatSessions,
  sessionsAfterLoad,
} from './chatSessionLoad.ts';
import { backendToSessionMeta } from './chatSessionMeta.ts';

test('initial session hydration has no clear-session call or unload beacon', async () => {
  const source = await readFile(new URL('./useChatSessions.ts', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /\.clearSession\s*\(/);
  assert.doesNotMatch(source, /sendBeacon\s*\(/);
});

test('a failed session load preserves existing sessions and a retry replaces them', async () => {
  const existingSessions = [{
    id: 'existing-id',
    title: 'Existing conversation',
    preview: '',
    language: 'spanish' as const,
    createdAt: '2026-07-18T10:00:00.000Z',
    updatedAt: '2026-07-18T10:00:00.000Z',
    messageCount: 2,
  }];
  let attempt = 0;
  const listConversations = async () => {
    attempt += 1;
    if (attempt === 1) {
      return { success: false, error: 'fetch failed' };
    }
    return {
      success: true,
      data: {
        conversations: [{
          id: 'recovered-id',
          title: 'Recovered conversation',
          language: 'spanish',
          created_at: '2026-07-18T11:00:00.000Z',
          message_count: 1,
        }],
        total_count: 1,
        active_count: 1,
      },
    };
  };

  const failed = await loadChatSessions(listConversations, backendToSessionMeta);
  assert.deepEqual(failed, { success: false, error: 'fetch failed' });
  assert.equal(sessionsAfterLoad(existingSessions, failed), existingSessions);

  const recovered = await loadChatSessions(listConversations, backendToSessionMeta);
  assert.equal(recovered.success, true);
  const sessions = sessionsAfterLoad(existingSessions, recovered);
  assert.equal(sessions.length, 1);
  assert.equal(sessions[0].id, 'recovered-id');
});
