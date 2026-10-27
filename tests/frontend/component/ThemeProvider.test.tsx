import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ThemeProvider, useTheme } from '../../../frontend/src/presentation/components/ThemeProvider';

test('tema guardado aplica clase oscura sin esconder hijos', async () => {
  localStorage.setItem('ia-juridica-theme', 'dark');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })));
  render(<ThemeProvider><p>Contenido visible</p></ThemeProvider>);
  expect(screen.getByText('Contenido visible')).toBeInTheDocument();
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  expect(localStorage.getItem('ia-juridica-theme')).toBe('dark');
});

test('tema guardado puede cambiarse y persistirse', async () => {
  localStorage.setItem('ia-juridica-theme', 'dark');
  function Toggle() {
    const { toggleTheme } = useTheme();
    return <button onClick={toggleTheme}>Cambiar tema</button>;
  }
  render(<ThemeProvider><Toggle /></ThemeProvider>);
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  fireEvent.click(screen.getByRole('button', { name: 'Cambiar tema' }));
  expect(document.documentElement).toHaveClass('light');
  expect(localStorage.getItem('ia-juridica-theme')).toBe('light');
});
