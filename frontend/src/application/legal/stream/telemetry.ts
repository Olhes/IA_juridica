/**
 * Telemetría del stream medida en el cliente: solo números y el `request_id`, nunca texto.
 * Se envía con `navigator.sendBeacon` (no bloquea, no reintenta y no lanza); si el navegador
 * no lo ofrece o el servidor es antiguo (sin `request_id` de 32 hex) simplemente no se envía.
 */
import type { StreamSummary } from './ndjsonParser';

export type StreamOutcome = 'final' | 'degraded' | 'error' | 'aborted' | 'incomplete';

export interface StreamTelemetryPayload {
  request_id: string;
  outcome: StreamOutcome;
  error_code?: string;
  ttfb_ms?: number;
  total_ms?: number;
  stage_ms: Record<string, number>;
  lines_valid: number;
  lines_invalid: number;
  lines_repaired: number;
  lines_duplicate: number;
  lines_out_of_order: number;
  lines_legacy: number;
  degraded: boolean;
}

const REQUEST_ID = /^[0-9a-f]{32}$/;
const MAX_MS = 600_000;

const clamp = (value: number) => Math.min(Math.max(Math.round(value * 10) / 10, 0), MAX_MS);

export function buildStreamTelemetry(summary: StreamSummary, outcome: StreamOutcome): StreamTelemetryPayload | null {
  if (!summary.requestId || !REQUEST_ID.test(summary.requestId)) return null;
  const stageMs: Record<string, number> = {};
  for (const [stage, ms] of Object.entries(summary.timings.stageMs)) {
    if (typeof ms === 'number' && Number.isFinite(ms)) stageMs[stage] = clamp(ms);
  }
  const { stats, timings } = summary;
  const cap = (value: number) => Math.min(value, 100_000);
  return {
    request_id: summary.requestId,
    outcome,
    ...(summary.error?.code ? { error_code: summary.error.code } : {}),
    ...(timings.firstByteMs !== null ? { ttfb_ms: clamp(timings.firstByteMs) } : {}),
    total_ms: clamp(timings.totalMs),
    stage_ms: stageMs,
    lines_valid: cap(stats.valid),
    lines_invalid: cap(stats.invalid),
    lines_repaired: cap(stats.repaired),
    lines_duplicate: cap(stats.duplicates),
    lines_out_of_order: cap(stats.outOfOrder),
    lines_legacy: cap(stats.legacy),
    degraded: summary.degraded,
  };
}

export function sendStreamTelemetry(apiBase: string, payload: StreamTelemetryPayload | null): boolean {
  try {
    if (!payload || typeof navigator === 'undefined' || typeof navigator.sendBeacon !== 'function') return false;
    // text/plain evita el preflight CORS; el servidor lee el cuerpo como JSON.
    return navigator.sendBeacon(`${apiBase}/telemetry/stream`, new Blob([JSON.stringify(payload)], { type: 'text/plain;charset=UTF-8' }));
  } catch {
    return false;
  }
}
