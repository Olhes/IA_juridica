import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { ProtectedRoute } from '../../../frontend/src/presentation/components/ProtectedRoute';
import { RegisterPage } from '../../../frontend/src/presentation/pages/RegisterPage';
import { LoginPage } from '../../../frontend/src/presentation/pages/LoginPage';
import { ChatWelcome } from '../../../frontend/src/presentation/components/chat/ChatWelcome';
import AuthCallback from '../../../frontend/app/auth/callback/page';
import HomePage, { metadata as homeMetadata } from '../../../frontend/app/page';
import LoginRoute from '../../../frontend/app/login/page';
import RegisterRoute from '../../../frontend/app/register/page';
import RootLayout, { metadata } from '../../../frontend/app/layout';

const state = vi.hoisted(() => ({ mounted: false, isAuthenticated: false }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('../../../frontend/src/presentation/components/AuthProvider', () => ({
  useAuth: () => state, AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
// La página de chat tiene su propia suite; aquí se verifica el entrypoint App Router.
vi.mock('../../../frontend/src/presentation/pages/ChatPage', () => ({ ChatPage: () => <div>Chat principal</div> }));
beforeEach(() => { vi.clearAllMocks(); state.mounted = false; state.isAuthenticated = false; });

test('ruta protegida espera hidratación redirige invitados y permite autenticados', () => {
  const { rerender } = render(<ProtectedRoute>Privado</ProtectedRoute>);
  expect(screen.queryByText('Privado')).not.toBeInTheDocument();
  expect(router.push).not.toHaveBeenCalled();
  state.mounted = true;
  rerender(<ProtectedRoute>Privado</ProtectedRoute>);
  expect(router.push).toHaveBeenCalledWith('/login');
  expect(screen.queryByText('Privado')).not.toBeInTheDocument();
  state.isAuthenticated = true;
  rerender(<ProtectedRoute>Privado</ProtectedRoute>);
  expect(screen.getByText('Privado')).toBeInTheDocument();
});
test('callback OAuth guarda indicador UI no token y vuelve a inicio', () => {
  render(<AuthCallback />);
  expect(localStorage.getItem('auth_just_logged_in')).toBe('true');
  expect(localStorage.getItem('token')).toBeNull();
  expect(router.replace).toHaveBeenCalledWith('/');
});
test('registro redirige al flujo login existente', () => {
  render(<RegisterPage />);
  expect(screen.getByText('Redirigiendo al login...')).toBeInTheDocument();
  expect(router.push).toHaveBeenCalledWith('/login');
});
test('login inicia OAuth y deshabilita reenvío durante navegación', () => {
  const location = { href: '' };
  vi.stubGlobal('window', Object.create(window, { location: { value: location } }));
  render(<LoginPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Acceder' }));
  expect(location.href).toBe('http://localhost:8000/auth/google');
  expect(screen.getByRole('button', { name: 'Conectando con Google...' })).toBeDisabled();
});
test.each(['spanish', 'quechua'] as const)('bienvenida %s ofrece seis consultas seleccionables', language => {
  const select = vi.fn();
  render(<ChatWelcome language={language} onSelectQuery={select} />);
  const buttons = screen.getAllByRole('button');
  expect(buttons).toHaveLength(6);
  buttons.forEach(button => fireEvent.click(button));
  expect(select).toHaveBeenCalledTimes(6);
  expect(select.mock.calls.every(([query]) => typeof query === 'string' && query.length > 10)).toBe(true);
});
test('entrypoints y layout conservan idioma proveedores y metadatos', () => {
  const element = RootLayout({ children: 'Contenido' });
  expect(element.type).toBe('html');
  expect(element.props.lang).toBe('es');
  expect(element.props.children.props.children.props.children.props.children).toBe('Contenido');
  expect(metadata.title).toContain('IA Jurídica');
  expect(homeMetadata.description).toContain('Quechua');
  render(<HomePage />);
  expect(screen.getByText('Chat principal')).toBeInTheDocument();
  expect(LoginRoute().type).toBe(LoginPage);
  expect(RegisterRoute().type).toBe(RegisterPage);
});
