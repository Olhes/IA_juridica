'use client';

import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGoogleLogin: () => void;
}

export function AuthModal({ isOpen, onClose, onGoogleLogin }: AuthModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !isOpen) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    return () => { if (dialog.open && typeof dialog.close === 'function') dialog.close(); };
  }, [isOpen]);

  if (!isOpen) return null;
  return (
    <dialog ref={dialogRef} aria-labelledby="auth-modal-title" onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="fixed inset-0 m-auto w-[min(90vw,480px)] rounded-[32px] bg-white p-8 text-center text-slate-900 shadow-2xl backdrop:bg-slate-900/70 sm:p-10">
      <button type="button" onClick={onClose} aria-label="Cerrar inicio de sesión"
        className="absolute right-6 top-6 flex h-12 w-12 items-center justify-center rounded-full border border-slate-300">
        <X className="h-6 w-6" aria-hidden="true" />
      </button>
      <h2 id="auth-modal-title" className="mb-2 text-3xl font-extrabold">Bienvenido a IA Jurídica</h2>
      <p className="mb-6 text-base">Inicia sesión para obtener orientación legal personalizada.</p>
      <button type="button" onClick={onGoogleLogin} autoFocus
        className="w-full rounded-full border-2 border-slate-300 py-3 font-bold hover:bg-slate-50">
        Continuar con Google
      </button>
    </dialog>
  );
}
