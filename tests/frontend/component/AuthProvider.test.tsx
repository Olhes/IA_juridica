import { test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../../frontend/src/presentation/components/AuthProvider';
import { authService } from '../../../frontend/src/application/legal/services/authService';
// These are synthetic sessions in jsdom, not the developer's browser cookies.
// Capture component debug logs locally; keep assertions, warnings and errors visible.
beforeEach(() => { vi.spyOn(console, 'log').mockImplementation(() => {}); });
afterEach(() => { vi.restoreAllMocks(); });
function Consumer() { const auth = useAuth(); return <p>{auth.isAuthenticated ? auth.user?.username : 'anónimo'}</p>; }
test('provider restaura usuario por cookies y limpia flag sin guardar tokens', async () => {
  vi.spyOn(authService, 'getCurrentUser').mockResolvedValue({ username: 'synthetic' } as any);
  vi.spyOn(authService, 'subscribe').mockImplementation(listener => { listener({ token: null, user: null, isAuthenticated: false }); return vi.fn(); });
  const update = vi.spyOn(authService, 'setState'); localStorage.setItem('auth_just_logged_in', 'true');
  render(<AuthProvider><Consumer /></AuthProvider>);
  await waitFor(() => expect(update).toHaveBeenCalledWith(expect.objectContaining({ token: 'from_cookie', isAuthenticated: true })));
  expect(localStorage.getItem('auth_just_logged_in')).toBeNull();
});
test('provider sesión simulada ausente mantiene estado anónimo sin fallar render', async () => {
  vi.spyOn(authService, 'getCurrentUser').mockResolvedValue(null);
  vi.spyOn(authService, 'subscribe').mockImplementation(listener => { listener({ token: null, user: null, isAuthenticated: false }); return vi.fn(); });
  render(<AuthProvider><Consumer /></AuthProvider>); expect(await screen.findByText('anónimo')).toBeVisible();
});
test('provider desmontado con sesión simulada elimina suscripción y listener storage', async () => {
  const off = vi.fn(); const get = vi.spyOn(authService, 'getCurrentUser').mockResolvedValue(null);
  vi.spyOn(authService, 'subscribe').mockReturnValue(off);
  const { unmount } = render(<AuthProvider><Consumer /></AuthProvider>); await act(async () => {}); unmount();
  const calls = get.mock.calls.length; window.dispatchEvent(new StorageEvent('storage', { key: 'auth_just_logged_in', newValue: 'true' }));
  expect(off).toHaveBeenCalledTimes(1); expect(get).toHaveBeenCalledTimes(calls);
});
test('provider callback Google simulado revalida sesión por storage y muestra usuario', async () => {
  const user = { id: 'google-user', email: 'ana@example.invalid', username: 'google-ana', picture: 'https://avatar.example.invalid/ana' };
  const get = vi.spyOn(authService, 'getCurrentUser').mockResolvedValueOnce(null).mockResolvedValue(user as any);
  let notify: Parameters<typeof authService.subscribe>[0];
  vi.spyOn(authService, 'subscribe').mockImplementation(listener => {
    notify = listener;
    listener({ token: null, user: null, isAuthenticated: false });
    return vi.fn();
  });
  const update = vi.spyOn(authService, 'setState').mockImplementation(state => {
    notify({ token: null, user: null, isAuthenticated: false, ...state });
  });
  render(<AuthProvider><Consumer /></AuthProvider>);
  await act(async () => {});
  expect(screen.getByText('anónimo')).toBeVisible();
  localStorage.setItem('auth_just_logged_in', 'true');
  act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'auth_just_logged_in', newValue: 'true' })));
  expect(await screen.findByText('google-ana')).toBeVisible();
  expect(get).toHaveBeenCalledTimes(2);
  expect(update).toHaveBeenCalledWith({ isAuthenticated: true, user, token: 'from_cookie' });
  expect(localStorage.getItem('auth_just_logged_in')).toBeNull();
  expect(localStorage.getItem('access_token')).toBeNull();
  expect(localStorage.getItem('refresh_token')).toBeNull();
});
