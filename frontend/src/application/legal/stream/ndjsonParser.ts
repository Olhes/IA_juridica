/**
 * Analizador puro del stream NDJSON v1 de `/legal-query-stream`.
 *
 * Sin estado oculto ni efectos: cada función recibe el estado y devuelve uno nuevo, y el reloj
 * llega como argumento (`now`, en milisegundos), de modo que las pruebas son deterministas.
 *
 * Tolera BOM, CRLF y líneas partidas entre lecturas; repara lo reparable (prefijo `data:`,
 * basura alrededor, varios objetos pegados) y descarta —contándolo— lo irrecuperable; deduplica
 * por `seq` y ordena por `seq` dentro de cada lectura; si falta el `final` usa el `chunk` y marca
 * la respuesta como `degraded`; mide los tiempos. Acepta los eventos antiguos sin `v`/`seq`.
 */
import type {
  ChunkEvent,
  ErrorEvent,
  FinalEvent,
  StageEvent,
  StreamEvent,
} from '../../../domain/legal/streamEvents.generated';

type StageName = StageEvent['stage'];
type ErrorCode = ErrorEvent['code'];

const ERROR_CODES: readonly ErrorCode[] = [
  'RETRIEVAL_UNAVAILABLE',
  'GENERATION_UNAVAILABLE',
  'TRANSLATION_UNAVAILABLE',
  'TIMEOUT',
  'INTERNAL_ERROR',
];
const STAGES: readonly StageName[] = ['translate_in', 'retrieval', 'generation', 'validation', 'translate_out'];
const MAX_BUFFER_CHARS = 8_000_000;

/** Evento sin `v`/`seq` que emitían versiones anteriores del servidor. */
export type LegacyEvent =
  | { legacy: true; seq: null; type: 'chunk'; delta: string }
  | { legacy: true; seq: null; type: 'final'; data: Record<string, unknown> }
  | { legacy: true; seq: null; type: 'error'; code?: ErrorCode; retryable?: boolean; error?: string };

export type AcceptedEvent = (StreamEvent & { legacy?: false }) | LegacyEvent;
export type TimedEvent = AcceptedEvent & { receivedAt: number };

export interface ParserStats {
  valid: number;
  invalid: number;
  repaired: number;
  duplicates: number;
  outOfOrder: number;
  legacy: number;
  unsupported: number;
}

export interface ParserState {
  readonly buffer: string;
  readonly startedAt: number;
  readonly firstByteAt: number | null;
  readonly started: boolean;
  readonly events: readonly TimedEvent[];
  readonly seen: readonly number[];
  readonly maxSeq: number;
  readonly requestId: string | null;
  readonly stats: ParserStats;
  readonly stageStarts: Readonly<Partial<Record<StageName, number>>>;
  readonly stageMs: Readonly<Partial<Record<StageName, number>>>;
}

export interface StreamTimings {
  /** Desde que se abrió la petición hasta el primer byte. */
  firstByteMs: number | null;
  firstChunkMs: number | null;
  /** Hasta el evento terminal (`final` o `error`). */
  terminalMs: number | null;
  totalMs: number;
  /** Duración por etapa: la informada por el servidor, o la observada por el cliente. */
  stageMs: Partial<Record<StageName, number>>;
}

export interface StreamSummary {
  requestId: string | null;
  final: FinalEvent | LegacyFinal | null;
  error: { code: ErrorCode | null; retryable: boolean } | null;
  /** Texto de los `chunk`, en orden de `seq`. */
  chunkText: string;
  /** Faltó el `final` pero hay texto: se usa el chunk y se avisa. */
  degraded: boolean;
  /** No llegó ni `final`, ni `error`, ni texto. */
  incomplete: boolean;
  missingDone: boolean;
  events: readonly TimedEvent[];
  stats: ParserStats;
  timings: StreamTimings;
}

type LegacyFinal = Extract<LegacyEvent, { type: 'final' }>;

const EMPTY_STATS: ParserStats = { valid: 0, invalid: 0, repaired: 0, duplicates: 0, outOfOrder: 0, legacy: 0, unsupported: 0 };

export function createParserState(now: number): ParserState {
  return {
    buffer: '',
    startedAt: now,
    firstByteAt: null,
    started: false,
    events: [],
    seen: [],
    maxSeq: -1,
    requestId: null,
    stats: EMPTY_STATS,
    stageStarts: {},
    stageMs: {},
  };
}

// ── Extracción de objetos JSON de una línea ────────────────────────────────

/** Objetos `{...}` balanceados de nivel superior de `line` (consciente de cadenas JSON). */
export function extractObjects(line: string): string[] {
  const found: string[] = [];
  let depth = 0;
  let start = -1;
  let inString = false;
  let escaped = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"' && depth > 0) inString = true;
    else if (char === '{') {
      if (depth === 0) start = index;
      depth += 1;
    } else if (char === '}' && depth > 0) {
      depth -= 1;
      if (depth === 0) found.push(line.slice(start, index + 1));
    }
  }
  return found;
}

interface ParsedLine {
  objects: unknown[];
  repaired: boolean;
  invalid: number;
}

function parseLine(raw: string): ParsedLine {
  const line = raw.replace(/^﻿/, '').trim();
  try {
    return { objects: [JSON.parse(line)], repaired: false, invalid: 0 };
  } catch {
    const pieces = extractObjects(line);
    const objects: unknown[] = [];
    let invalid = pieces.length === 0 ? 1 : 0;
    for (const piece of pieces) {
      try {
        objects.push(JSON.parse(piece));
      } catch {
        invalid += 1;
      }
    }
    return { objects, repaired: objects.length > 0, invalid };
  }
}

// ── Validación de eventos ─────────────────────────────────────────────────

type Verdict = { kind: 'ok'; event: AcceptedEvent } | { kind: 'unsupported' } | { kind: 'invalid' };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

function validate(value: unknown): Verdict {
  if (!isRecord(value) || typeof value.type !== 'string') return { kind: 'invalid' };
  if (value.v === undefined && value.seq === undefined) return validateLegacy(value);
  if (value.v !== 1) return { kind: 'unsupported' };
  if (!Number.isInteger(value.seq) || (value.seq as number) < 0 || typeof value.request_id !== 'string') {
    return { kind: 'invalid' };
  }
  switch (value.type) {
    case 'meta':
    case 'final':
      return isRecord(value.data) ? { kind: 'ok', event: value as unknown as StreamEvent } : { kind: 'invalid' };
    case 'stage':
      return STAGES.includes(value.stage as StageName) && (value.status === 'start' || value.status === 'end')
        ? { kind: 'ok', event: value as unknown as StreamEvent }
        : { kind: 'invalid' };
    case 'chunk':
      return typeof value.delta === 'string' ? { kind: 'ok', event: value as unknown as ChunkEvent } : { kind: 'invalid' };
    case 'error':
      return ERROR_CODES.includes(value.code as ErrorCode) && typeof value.retryable === 'boolean'
        ? { kind: 'ok', event: value as unknown as ErrorEvent }
        : { kind: 'invalid' };
    case 'done':
      return { kind: 'ok', event: value as unknown as StreamEvent };
    default:
      return { kind: 'invalid' };
  }
}

function validateLegacy(value: Record<string, unknown>): Verdict {
  if (value.type === 'chunk' && typeof value.delta === 'string') {
    return { kind: 'ok', event: { legacy: true, seq: null, type: 'chunk', delta: value.delta } };
  }
  if (value.type === 'final' && isRecord(value.data)) {
    return { kind: 'ok', event: { legacy: true, seq: null, type: 'final', data: value.data } };
  }
  if (value.type === 'error') {
    const code = ERROR_CODES.includes(value.code as ErrorCode) ? (value.code as ErrorCode) : undefined;
    return {
      kind: 'ok',
      event: {
        legacy: true,
        seq: null,
        type: 'error',
        code,
        retryable: value.retryable === true,
        error: typeof value.error === 'string' ? value.error : undefined,
      },
    };
  }
  return { kind: 'invalid' };
}

// ── Núcleo ────────────────────────────────────────────────────────────────

function ingest(state: ParserState, lines: string[], now: number): { state: ParserState; accepted: TimedEvent[] } {
  const stats = { ...state.stats };
  const candidates: AcceptedEvent[] = [];
  for (const raw of lines) {
    if (!raw.trim()) continue;
    const parsed = parseLine(raw);
    stats.invalid += parsed.invalid;
    if (parsed.repaired) stats.repaired += 1;
    for (const object of parsed.objects) {
      const verdict = validate(object);
      if (verdict.kind === 'unsupported') stats.unsupported += 1;
      else if (verdict.kind === 'invalid') stats.invalid += 1;
      else candidates.push(verdict.event);
    }
  }
  // Dentro de una lectura se ordena por `seq`; los eventos antiguos (sin seq) conservan su posición.
  const versioned = candidates
    .filter((event) => event.seq !== null)
    .sort((a, b) => (a.seq as number) - (b.seq as number));
  const legacy = candidates.filter((event) => event.seq === null);
  const ordered: AcceptedEvent[] = [...versioned, ...legacy];

  const seen = [...state.seen];
  let maxSeq = state.maxSeq;
  let requestId = state.requestId;
  const accepted: TimedEvent[] = [];
  for (const event of ordered) {
    if (event.seq === null) {
      stats.legacy += 1;
      stats.valid += 1;
      accepted.push({ ...event, receivedAt: now });
      continue;
    }
    const identity = (event as StreamEvent).request_id;
    if (requestId !== null && identity !== requestId) {
      stats.invalid += 1;
      continue;
    }
    if (seen.includes(event.seq)) {
      stats.duplicates += 1;
      continue;
    }
    requestId = identity;
    if (event.seq < maxSeq) stats.outOfOrder += 1;
    maxSeq = Math.max(maxSeq, event.seq);
    seen.push(event.seq);
    stats.valid += 1;
    accepted.push({ ...event, receivedAt: now });
  }

  const stageStarts = { ...state.stageStarts };
  const stageMs = { ...state.stageMs };
  for (const event of accepted) {
    if (event.type !== 'stage' || event.legacy) continue;
    if (event.status === 'start') stageStarts[event.stage] = event.receivedAt;
    else {
      const observed = stageStarts[event.stage] !== undefined ? event.receivedAt - (stageStarts[event.stage] as number) : undefined;
      const duration = typeof event.elapsed_ms === 'number' ? event.elapsed_ms : observed;
      if (duration !== undefined) stageMs[event.stage] = (stageMs[event.stage] ?? 0) + duration;
    }
  }
  return {
    state: { ...state, events: [...state.events, ...accepted], seen, maxSeq, requestId, stats, stageStarts, stageMs },
    accepted,
  };
}

/** Procesa un trozo de texto del stream y devuelve el estado nuevo y los eventos aceptados. */
export function pushChunk(state: ParserState, text: string, now: number): { state: ParserState; accepted: TimedEvent[] } {
  let incoming = text;
  const first = !state.started && incoming.length > 0;
  if (first) incoming = incoming.replace(/^﻿/, '');
  const combined = state.buffer + incoming;
  const parts = combined.split(/\r\n|\n|\r(?!$)/);
  let remainder = parts.pop() ?? '';
  if (remainder.length > MAX_BUFFER_CHARS) remainder = '';
  const base: ParserState = {
    ...state,
    buffer: remainder,
    started: state.started || incoming.length > 0,
    firstByteAt: state.firstByteAt ?? (incoming.length > 0 ? now : null),
  };
  return ingest(base, parts, now);
}

/** Cierra el stream: procesa una última línea sin salto final y resume lo ocurrido. */
export function finishStream(state: ParserState, now: number): { state: ParserState; accepted: TimedEvent[]; summary: StreamSummary } {
  const tail = state.buffer.replace(/\r$/, '');
  const flushed = ingest({ ...state, buffer: '' }, tail.trim() ? [tail] : [], now);
  return { ...flushed, summary: summarise(flushed.state, now) };
}

export function summarise(state: ParserState, now: number): StreamSummary {
  const events = [...state.events].sort((a, b) => {
    if (a.seq === null || b.seq === null) return 0;
    return a.seq - b.seq;
  });
  const chunks = events.filter((event): event is TimedEvent & { type: 'chunk'; delta: string } => event.type === 'chunk');
  const final = (events.find((event) => event.type === 'final') as FinalEvent | LegacyFinal | undefined) ?? null;
  const errorEvent = events.find((event) => event.type === 'error') as (TimedEvent & { type: 'error' }) | undefined;
  const chunkText = chunks.map((event) => event.delta).join('');
  const terminal = events.find((event) => event.type === 'final' || event.type === 'error');
  const firstChunk = chunks[0];
  const degraded = final === null && errorEvent === undefined && chunkText.length > 0;
  return {
    requestId: state.requestId,
    final,
    error: errorEvent
      ? { code: (errorEvent as { code?: ErrorCode }).code ?? null, retryable: Boolean((errorEvent as { retryable?: boolean }).retryable) }
      : null,
    chunkText,
    degraded,
    incomplete: final === null && errorEvent === undefined && chunkText.length === 0,
    missingDone: !events.some((event) => event.type === 'done') && !events.every((event) => event.seq === null),
    events,
    stats: state.stats,
    timings: {
      firstByteMs: state.firstByteAt === null ? null : state.firstByteAt - state.startedAt,
      firstChunkMs: firstChunk ? firstChunk.receivedAt - state.startedAt : null,
      terminalMs: terminal ? terminal.receivedAt - state.startedAt : null,
      totalMs: now - state.startedAt,
      stageMs: { ...state.stageMs },
    },
  };
}

/** Atajo para pruebas y utilidades: procesa un texto completo ya recibido. */
export function parseWholeStream(text: string, now = 0): StreamSummary {
  const pushed = pushChunk(createParserState(now), text, now);
  return finishStream(pushed.state, now).summary;
}
