import { test, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { AuthService } from '../../../frontend/src/application/legal/services/authService';
import { server, API } from '../fixtures/server';
const user = { id: 'synthetic', username: 'test', email: 'test@example.invalid', roles: [], role: 'user', is_active: true };

test('login por cookie actualiza estado sin persistir tokens', async () => {
  const api = new AuthService(); const writes = vi.spyOn(Storage.prototype, 'setItem');
  server.use(http.post(`${API}/auth/login`, async ({ request }) => {
    expect(request.credentials).toBe('include'); expect((await request.formData()).get('username')).toBe('test');
    return HttpResponse.json({ message: 'ok' });
  }), http.get(`${API}/auth/me`, () => HttpResponse.json(user)));
  await api.login({ username: 'test', password: 'synthetic' });
  expect(api.isAuthenticated).toBe(true); expect(api.currentUser).toEqual(user); expect(writes).not.toHaveBeenCalled();
});
test('usuario se recupera desde cookies tras nueva instancia sin token JS', async () => {
  server.use(http.get(`${API}/auth/me`, ({ request }) => {
    expect(request.credentials).toBe('include'); return HttpResponse.json(user);
  }));
  const api = new AuthService(); expect(await api.getCurrentUser()).toEqual(user);
  expect(api.isAuthenticated).toBe(true);
});
test('login inválido no autentica y conserva mensaje de error', async () => {
  server.use(http.post(`${API}/auth/login`, () => HttpResponse.json({ detail: 'Inválido' }, { status: 401 })));
  const api = new AuthService(); await expect(api.login({ username: 'x', password: 'x' })).rejects.toThrow('Inválido');
  expect(api.isAuthenticated).toBe(false);
});
test('logout limpia estado y notifica aunque la red falle', async () => {
  server.use(http.post(`${API}/auth/logout`, () => HttpResponse.error()));
  const api = new AuthService(); const listener = vi.fn(); const off = api.subscribe(listener);
  api.setState({ isAuthenticated: true, token: 'from_cookie', user }); await api.logout();
  expect(api.getState()).toEqual({ isAuthenticated: false, token: null, user: null });
  off(); const calls = listener.mock.calls.length; api.setState({ isAuthenticated: false, token: null, user: null });
  expect(listener).toHaveBeenCalledTimes(calls);
});
test('401 refresca cookie una vez y reintenta conservando opciones', async () => {
  let requests = 0; let refreshes = 0;
  server.use(http.post(`${API}/auth/refresh`, ({ request }) => {
    refreshes++; expect(request.credentials).toBe('include'); return HttpResponse.json({ access_token: 'synthetic' });
  }), http.post(`${API}/protected`, async ({ request }) => {
    expect(await request.json()).toEqual({ value: 1 });
    return ++requests === 1 ? new HttpResponse(null, { status: 401 }) : HttpResponse.json({ ok: true });
  }));
  expect(await new AuthService().authenticatedRequest('/protected', { method: 'POST', body: '{"value":1}' })).toEqual({ ok: true });
  expect(refreshes).toBe(1); expect(requests).toBe(2);
});
test('401 persistente no causa bucle de refresh y termina sesión', async () => {
  let refreshes = 0;
  server.use(http.post(`${API}/auth/refresh`, () => {
    refreshes++; if (refreshes > 2) throw new Error('Bucle detectado'); return HttpResponse.json({});
  }), http.get(`${API}/protected`, () => new HttpResponse(null, { status: 401 })),
  http.post(`${API}/auth/logout`, () => HttpResponse.json({})));
  const api = new AuthService(); api.setState({ isAuthenticated: true, token: 'from_cookie', user });
  await expect(api.authenticatedRequest('/protected')).rejects.toThrow();
  expect(refreshes).toBe(1); expect(api.isAuthenticated).toBe(false);
});
test('refresh fallido cierra sesión sin filtrar credenciales', async () => {
  server.use(http.post(`${API}/auth/refresh`, () => new HttpResponse(null, { status: 401 })),
    http.get(`${API}/protected`, () => new HttpResponse(null, { status: 401 })),
    http.post(`${API}/auth/logout`, () => HttpResponse.json({})));
  const api = new AuthService(); api.setState({ isAuthenticated: true, token: 'from_cookie', user });
  await expect(api.authenticatedRequest('/protected')).rejects.toThrow('Sesión expirada'); expect(api.isAuthenticated).toBe(false);
});
