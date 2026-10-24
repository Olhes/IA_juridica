// Login con Google en una ventana emergente: la pestaña original no navega.
// /auth/callback marca `auth_just_logged_in` en localStorage y se cierra; el
// AuthProvider de esta pestaña escucha ese evento `storage` y revalida la sesión.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function openGoogleLoginPopup(): void {
  const authUrl = `${API_BASE}/auth/google`;
  const width = 500;
  const height = 600;
  const left = window.screenX + (window.outerWidth - width) / 2;
  const top = window.screenY + (window.outerHeight - height) / 2;

  const popup = window.open(
    authUrl,
    'google-auth',
    `width=${width},height=${height},left=${left},top=${top},resizable,scrollbars=yes,status=1`
  );

  // Ventanas emergentes bloqueadas: login en la misma pestaña (vuelve vía /auth/callback).
  if (!popup) {
    window.location.href = authUrl;
    return;
  }
  popup.focus();
}
