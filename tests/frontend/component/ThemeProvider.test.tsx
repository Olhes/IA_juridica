import { act, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ThemeProvider } from '../../../frontend/src/presentation/components/ThemeProvider';

test('tema guardado aplica clase oscura sin esconder hijos', async () => {
  localStorage.setItem('theme', 'dark');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })));
  render(<ThemeProvider><p>Contenido visible</p></ThemeProvider>);
  expect(screen.getByText('Contenido visible')).toBeInTheDocument();
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  expect(localStorage.getItem('theme')).toBe('dark');
});

test('tema del sistema sigue cambios y libera listener al desmontar', async () => {
  localStorage.setItem('theme', 'system');
  const callbacks: Array<(event: { matches: boolean }) => void> = [];
  const remove = vi.fn();
  const media = { matches: false, addListener: (fn: (event: { matches: boolean }) => void) => callbacks.push(fn), removeListener: remove };
  vi.stubGlobal('matchMedia', vi.fn(() => media));
  const { unmount } = render(<ThemeProvider>Contenido</ThemeProvider>);
  await waitFor(() => expect(document.documentElement).toHaveClass('light'));
  expect(callbacks).toHaveLength(1);
  act(() => { media.matches = true; callbacks[0]({ matches: true }); });
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  unmount();
  expect(remove).toHaveBeenCalledWith(callbacks[0]);
});
