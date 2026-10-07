import { test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MarkdownRenderer } from '../../../frontend/src/presentation/components/chat/MarkdownRenderer';
test('Markdown renderiza listas tablas enlaces y Unicode sin perder contenido', () => {
  render(<MarkdownRenderer content={'# Ñawpaq\n\n- á 🦙\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n[Fuente](https://example.invalid)'} />);
  expect(screen.getByRole('heading', { name: 'Ñawpaq' })).toBeVisible(); expect(screen.getByRole('table')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Fuente' })).toHaveAttribute('rel', 'noopener noreferrer'); expect(screen.getByText('á 🦙')).toBeVisible();
});
test('Markdown no ejecuta HTML scripts ni enlaces javascript del modelo', () => {
  const { container } = render(<MarkdownRenderer content={'<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n\n[malicioso](javascript:alert%281%29)'} />);
  expect(container.querySelector('script')).toBeNull(); expect(container.querySelector('[onerror]')).toBeNull();
  expect(screen.getByText('malicioso').getAttribute('href')).not.toMatch(/^javascript:/);
});
test('Markdown tolera contenido vacío e incompleto durante streaming', () => {
  const { rerender } = render(<MarkdownRenderer content="" isStreaming />);
  rerender(<MarkdownRenderer content="**texto incompleto" isStreaming />); expect(screen.getByText(/texto incompleto/)).toBeVisible();
});
