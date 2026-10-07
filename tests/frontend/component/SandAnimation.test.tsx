import { test, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { SandAnimation } from '../../../frontend/src/presentation/components/SandAnimation';

function animation(reduced = false, hasContext = true) {
  vi.stubGlobal('innerWidth', 96);
  vi.stubGlobal('innerHeight', 96);
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: reduced })));
  const queue = new Map<number, FrameRequestCallback>();
  let id = 0;
  const request = vi.fn((callback: FrameRequestCallback) => {
    queue.set(++id, callback);
    return id;
  });
  const cancel = vi.fn((key: number) => queue.delete(key));
  vi.stubGlobal('requestAnimationFrame', request);
  vi.stubGlobal('cancelAnimationFrame', cancel);
  const context = { setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(), save: vi.fn(), restore: vi.fn(), getImageData: vi.fn(() => {
    const data = new Uint8ClampedArray(96 * 96 * 4);
    for (const x of [31, 34, 37]) for (const y of [31, 34]) data[(y * 96 + x) * 4 + 3] = 255;
    return { data };
  }) };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    hasContext ? context as unknown as CanvasRenderingContext2D : null,
  );
  vi.spyOn(Math, 'random').mockReturnValue(0.01);
  let now = performance.now();
  function frame() {
    const entry = queue.entries().next().value;
    if (!entry) return false;
    queue.delete(entry[0]);
    now += 33;
    entry[1](now);
    return true;
  }
  return { context, queue, request, cancel, frame };
}

test('movimiento reducido termina una vez sin canvas ni RAF', () => {
  const engine = animation(true);
  const complete = vi.fn();
  render(<SandAnimation onComplete={complete} />);
  expect(complete).toHaveBeenCalledTimes(1);
  expect(engine.request).not.toHaveBeenCalled();
});
test('canvas no disponible permite continuar sin bloquear la interfaz', () => {
  const engine = animation(false, false);
  const complete = vi.fn();
  render(<SandAnimation onComplete={complete} />);
  expect(complete).toHaveBeenCalledTimes(1);
  expect(engine.request).not.toHaveBeenCalled();
});
test('ciclo simulado dibuja cae reforma y termina una sola vez', () => {
  const engine = animation();
  const complete = vi.fn();
  render(<SandAnimation onComplete={complete} />);
  for (let i = 0; i < 700 && engine.queue.size; i++) engine.frame();
  expect(engine.context.fillRect).toHaveBeenCalled();
  expect(engine.context.fillText).toHaveBeenCalledWith('Bienvenido a IA Jurídica', expect.any(Number), expect.any(Number));
  expect(complete).toHaveBeenCalledTimes(1);
  expect(engine.queue.size).toBe(0);
});
test('desmontar cancela el frame pendiente y libera resize', () => {
  const engine = animation();
  const complete = vi.fn();
  const { unmount } = render(<SandAnimation onComplete={complete} />);
  engine.frame();
  const pending = [...engine.queue.keys()][0];
  const calls = engine.context.setTransform.mock.calls.length;
  unmount();
  fireEvent(window, new Event('resize'));
  expect(engine.cancel).toHaveBeenCalledWith(pending);
  expect(engine.queue.size).toBe(0);
  expect(engine.context.setTransform).toHaveBeenCalledTimes(calls);
  expect(complete).not.toHaveBeenCalled();
});
test('resize cambia dimensiones sin reconstruir la máscara inicial', () => {
  const engine = animation();
  const { container } = render(<SandAnimation />);
  vi.stubGlobal('innerWidth', 120);
  fireEvent(window, new Event('resize'));
  expect(container.querySelector('canvas')).toHaveAttribute('width', String(120 * Math.min(window.devicePixelRatio || 1, 2)));
  expect(engine.context.getImageData).toHaveBeenCalledTimes(1);
});

test('animación sin callback también se detiene tras un ciclo', () => {
  const engine = animation();
  render(<SandAnimation />);
  for (let i = 0; i < 700 && engine.queue.size; i++) engine.frame();
  expect(engine.queue.size).toBe(0);
});
