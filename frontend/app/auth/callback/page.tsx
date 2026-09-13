'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    // Marcar que el usuario acaba de hacer login
    localStorage.setItem('auth_just_logged_in', 'true');

    // Redirigir inmediatamente a la página principal
    router.replace('/');
  }, [router]);

  return null;
}
