'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export function RegisterPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirigir al login con Google OAuth
    router.push('/login');
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500 mb-4"></div>
        <p className="text-white text-lg">Redirigiendo al login...</p>
      </div>
    </div>
  );
}
