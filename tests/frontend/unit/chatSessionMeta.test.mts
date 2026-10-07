import assert from 'node:assert/strict';
import { test } from 'vitest';

import { backendToSessionMeta } from '../../../frontend/src/application/legal/use-cases/chatSessionMeta.ts';

test('preserves the API message count when mapping session metadata', () => {
  const session = backendToSessionMeta({
    id: 'conversation-id',
    language: 'spanish',
    title: 'Existing conversation',
    created_at: '2026-07-18T10:00:00.000Z',
    message_count: 2,
  });

  assert.equal(session.messageCount, 2);
});

test('treats a missing API message count as an empty session', () => {
  const session = backendToSessionMeta({
    id: 'new-conversation-id',
    language: 'spanish',
    created_at: '2026-07-18T10:00:00.000Z',
  });

  assert.equal(session.messageCount, 0);
});
