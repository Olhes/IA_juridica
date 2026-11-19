import { expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthModal } from '../../../frontend/src/presentation/components/AuthModal';

test('modal de acceso ofrece Google y cierra por cancelación', async () => {
  const onClose = vi.fn(); const onGoogleLogin = vi.fn();
  render(<AuthModal isOpen onClose={onClose} onGoogleLogin={onGoogleLogin} />);
  const dialog = screen.getByRole('dialog', { name: 'Bienvenido a IA Jurídica' });
  expect(screen.queryByPlaceholderText('Contraseña')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Continuar con Google' }));
  expect(onGoogleLogin).toHaveBeenCalledOnce();
  fireEvent(dialog, new Event('cancel', { cancelable: true }));
  expect(onClose).toHaveBeenCalledOnce();
});
