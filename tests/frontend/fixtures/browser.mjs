// Synthetic API scoped to one browser page; never proxies a real backend.
export async function mockApi(page) {
  const conversations = new Map(); const calls = []; let sequence = 0;
  await page.route('**/*', async route => {
    const request = route.request(); const url = new URL(request.url());
    if (url.port !== '8000') {
      if (url.hostname === 'localhost' && url.port === '3100') return route.continue();
      return route.abort();
    }
    calls.push({ path: url.pathname, method: request.method() });
    const headers = { 'Access-Control-Allow-Origin': request.headers().origin || 'http://localhost:3100',
      'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'content-type',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS' };
    const json = (body, status = 200) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() === 'OPTIONS') return json({});
    if (url.pathname === '/session/bootstrap') return json({ principal_id: 'synthetic' });
    if (url.pathname === '/auth/me') return json({ detail: 'Anónimo' }, 401);
    if (url.pathname === '/health') return json({ status: 'healthy' });
    if (url.pathname === '/chat/conversations') {
      if (request.method() === 'GET') return json({ conversations: [...conversations.values()], total_count: conversations.size });
      const input = request.postDataJSON(); const item = { id: `synthetic-${++sequence}`, title: input.title, language: input.language,
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 0, messages: [] };
      conversations.set(item.id, item); return json(item);
    }
    if (url.pathname.startsWith('/chat/conversations/')) {
      const id = url.pathname.split('/').at(-1); const item = conversations.get(id);
      if (!item) return json({ detail: 'Not found' }, 404);
      if (request.method() === 'DELETE') { conversations.delete(id); return json({ success: true }); }
      if (request.method() === 'PUT') { Object.assign(item, request.postDataJSON()); return json(item); }
      return json({ conversation: item, messages: item.messages, total_messages: item.messages.length });
    }
    if (url.pathname === '/legal-query-stream') {
      const input = request.postDataJSON(); const item = conversations.get(input.conversation_id);
      if (!item) return json({ detail: 'Not found' }, 404);
      const response = input.language === 'quechua' ? 'Kutichiy sintético 🦙' : 'Respuesta sintética á 🦙';
      item.messages.push({ id: `${item.id}-user`, role: 'user', content: input.query, created_at: new Date().toISOString() },
        { id: `${item.id}-assistant`, role: 'assistant', content: response, created_at: new Date().toISOString() });
      item.message_count = item.messages.length;
      return route.fulfill({ headers, contentType: 'application/x-ndjson', body:
        JSON.stringify({ type: 'chunk', delta: response }) + '\n' + JSON.stringify({ type: 'final', data: {
          query: input.query, sources: [], response: { respuesta_espanol: response, respuesta_quechua: response },
        } }) + '\n' });
    }
    throw new Error(`Endpoint sin mock: ${request.method()} ${url.pathname}`);
  });
  return { conversations, calls };
}
