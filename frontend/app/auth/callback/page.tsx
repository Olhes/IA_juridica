'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    // Marcar que el usuario acaba de hacer login: la pestaña que abrió el popup
    // recibe el evento `storage` y revalida la sesión sin recargar.
    localStorage.setItem('auth_just_logged_in', 'true');

    // Abierto como popup desde la app: cerrarlo y dejar la sesión en la pestaña original.
    if (window.opener && !window.opener.closed) {
      window.close();
      return;
    }

    // Login en la misma pestaña (popup bloqueado): volver a la página principal.
    router.replace('/');
  }, [router]);

  return null;
}
