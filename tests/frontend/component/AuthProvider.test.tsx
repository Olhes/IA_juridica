import { test, expect, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../../frontend/src/presentation/components/AuthProvider';
import { authService } from '../../../frontend/src/application/legal/services/authService';
function Consumer() { const auth = useAuth(); return <p>{auth.isAuthenticated ? auth.user?.username : 'anónimo'}</p>; }
test('provider restaura usuario por cookies y limpia flag sin guardar tokens', async () => {
  vi.spyOn(authService, 'getCurrentUser').mockResolvedValue({ username: 'synthetic' } as any);
  vi.spyOn(authService, 'subscribe').mockImplementation(listener => { listener({ token: null, user: null, isAuthenticated: false }); return vi.fn(); });
  const update = vi.spyOn(authService, 'setState'); localStorage.setItem('auth_just_logged_in', 'true');
  render(<AuthProvider><Consumer /></AuthProvider>);
  await waitFor(() => expect(update).toHaveBeenCalledWith(expect.objectContaining({ token: 'from_cookie', isAuthenticated: true })));
  expect(localStorage.getItem('auth_just_logged_in')).toBeNull();
});
test('provider sesión ausente mantiene estado anónimo sin fallar render', async () => {
  vi.spyOn(authService, 'getCurrentUser').mockResolvedValue(null);
  vi.spyOn(authService, 'subscribe').mockImplementation(listener => { listener({ token: null, user: null, isAuthenticated: false }); return vi.fn(); });
  render(<AuthProvider><Consumer /></AuthProvider>); expect(await screen.findByText('anónimo')).toBeVisible();
});
test('provider desmontado elimina suscripción y listener storage', async () => {
  const off = vi.fn(); const get = vi.spyOn(authService, 'getCurrentUser').mockResolvedValue(null);
  vi.spyOn(authService, 'subscribe').mockReturnValue(off);
  const { unmount } = render(<AuthProvider><Consumer /></AuthProvider>); await act(async () => {}); unmount();
  const calls = get.mock.calls.length; window.dispatchEvent(new StorageEvent('storage', { key: 'auth_just_logged_in', newValue: 'true' }));
  expect(off).toHaveBeenCalledTimes(1); expect(get).toHaveBeenCalledTimes(calls);
});
