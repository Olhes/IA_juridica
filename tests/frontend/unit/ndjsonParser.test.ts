import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect } from 'vitest';
import {
  createParserState,
  extractObjects,
  finishStream,
  parseWholeStream,
  pushChunk,
  summarise,
  type StreamSummary,
} from '../../../frontend/src/application/legal/stream/ndjsonParser';
import { buildStreamTelemetry, sendStreamTelemetry } from '../../../frontend/src/application/legal/stream/telemetry';

// vitest se ejecuta desde la raíz del repositorio (ver scripts/run-tests.mjs).
const DIR = join(process.cwd(), 'tests', 'backend', 'fixtures', 'gold', 'ndjson_broken');
const manifest = JSON.parse(readFileSync(join(DIR, 'manifest.json'), 'utf8')) as Record<string, { expected: Record<string, unknown> }>;
const read = (name: string) => readFileSync(join(DIR, name), 'utf8');

const finalText = (summary: StreamSummary) => {
  const response = (summary.final?.data as { response?: { respuesta_espanol?: string } } | undefined)?.response;
  return response?.respuesta_espanol ?? null;
};
const shape = (summary: StreamSummary) => ({
  final_text: finalText(summary),
  chunk_text: summary.chunkText,
  degraded: summary.degraded,
  incomplete: summary.incomplete,
  error_code: summary.error?.code ?? null,
  missing_done: summary.missingDone,
  invalid: summary.stats.invalid,
  repaired: summary.stats.repaired,
  duplicates: summary.stats.duplicates,
  unsupported: summary.stats.unsupported,
  legacy: summary.stats.legacy,
  out_of_order: summary.stats.outOfOrder,
  valid: summary.stats.valid,
});

/** Generador pseudoaleatorio determinista (mulberry32). */
function rng(seed: number) {
  let t = seed;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function streamInPieces(text: string, cuts: number[]): StreamSummary {
  const bytes = new TextEncoder().encode(text);
  const decoder = new TextDecoder();
  let state = createParserState(0);
  let last = 0;
  for (const cut of [...cuts, bytes.length]) {
    state = pushChunk(state, decoder.decode(bytes.slice(last, cut), { stream: true }), 1).state;
    last = cut;
  }
  state = pushChunk(state, decoder.decode(), 1).state;
  return finishStream(state, 2).summary;
}

test('cada stream de referencia produce lo que declara su manifiesto', () => {
  const names = readdirSync(DIR).filter((name) => name.endsWith('.ndjson')).sort();
  expect(names).toEqual(Object.keys(manifest).sort());
  for (const name of names) {
    expect({ name, ...shape(parseWholeStream(read(name))) }).toEqual({ name, ...manifest[name].expected });
  }
});

test('tolera BOM y CRLF y entrega el mismo resultado que el stream limpio', () => {
  const clean = parseWholeStream(read('valid.ndjson'));
  const dirty = parseWholeStream(read('bom_crlf.ndjson'));
  expect(shape(dirty)).toEqual(shape(clean));
  expect(read('bom_crlf.ndjson').startsWith('﻿')).toBe(true);
});

test('el resultado no depende de dónde se parta el stream, ni siquiera en medio de un carácter UTF-8', () => {
  const text = read('valid.ndjson');
  const total = new TextEncoder().encode(text).length;
  const whole = shape(parseWholeStream(text));
  expect(whole.final_text).toBe('Respuesta final validada ñ 🦙');
  for (let cut = 1; cut < total; cut += 1) {
    expect(shape(streamInPieces(text, [cut]))).toEqual(whole);
  }
  expect(shape(streamInPieces(text, Array.from({ length: total - 1 }, (_, i) => i + 1)))).toEqual(whole);
});

test('un CRLF partido entre dos lecturas no genera líneas fantasma', () => {
  const text = read('bom_crlf.ndjson');
  const index = new TextEncoder().encode(text).indexOf(13);
  const summary = streamInPieces(text, [index + 1]);
  expect(summary.stats.invalid).toBe(0);
  expect(shape(summary)).toEqual(shape(parseWholeStream(read('valid.ndjson'))));
});

test('fuzz: cortes aleatorios en cualquier stream de referencia dan el mismo resultado', () => {
  const random = rng(7);
  for (const name of Object.keys(manifest)) {
    const text = read(name);
    const total = new TextEncoder().encode(text).length;
    const whole = shape(parseWholeStream(text));
    for (let round = 0; round < 25; round += 1) {
      const cuts = Array.from({ length: Math.floor(random() * 6) }, () => Math.floor(random() * (total + 1))).sort((a, b) => a - b);
      const piecewise = shape(streamInPieces(text, cuts));
      // Con cortes, un evento tardío cuenta como desordenado; el resto del resultado no cambia.
      expect({ ...piecewise, out_of_order: 0 }).toEqual({ ...whole, out_of_order: 0 });
    }
  }
});

test('fuzz: corrupción aleatoria nunca lanza y las cuentas son coherentes', () => {
  const random = rng(42);
  const base = read('valid.ndjson');
  for (let round = 0; round < 300; round += 1) {
    const characters = Array.from(base);
    for (let edit = 0; edit < 1 + Math.floor(random() * 8); edit += 1) {
      const at = Math.floor(random() * characters.length);
      const kind = random();
      if (kind < 0.4) characters.splice(at, 1);
      else if (kind < 0.7) characters.splice(at, 0, ['{', '}', '"', '\n', '\r', ',', '\u0000', '﻿'][Math.floor(random() * 8)]);
      else characters[at] = String.fromCharCode(32 + Math.floor(random() * 90));
    }
    const summary = parseWholeStream(characters.join(''));
    const { stats } = summary;
    expect(Object.values(stats).every((value) => Number.isInteger(value) && value >= 0)).toBe(true);
    expect(summary.events.length).toBe(stats.valid);
    expect(summary.degraded && summary.final !== null).toBe(false);
    expect(summary.incomplete && (summary.final !== null || summary.chunkText.length > 0)).toBe(false);
    if (summary.requestId) expect(summary.events.every((event) => event.seq === null || (event as { request_id: string }).request_id === summary.requestId)).toBe(true);
  }
});

test('fuzz: mezclar líneas y duplicarlas conserva el contenido y cuenta los duplicados', () => {
  const random = rng(99);
  const lines = read('valid.ndjson').trim().split('\n');
  for (let round = 0; round < 100; round += 1) {
    const shuffled = [...lines].sort(() => random() - 0.5);
    const duplicated = [...shuffled, ...lines.filter(() => random() < 0.3)];
    const summary = parseWholeStream(duplicated.join('\n') + '\n');
    expect(summary.chunkText).toBe('Respuesta final validada ñ 🦙');
    expect(finalText(summary)).toBe('Respuesta final validada ñ 🦙');
    expect(summary.stats.valid).toBe(lines.length);
    expect(summary.stats.duplicates).toBe(duplicated.length - lines.length);
    expect(summary.events.map((event) => event.seq)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  }
});

test('ordena por seq dentro de cada lectura y cuenta como desordenado lo que llega tarde', () => {
  const lines = read('valid.ndjson').trim().split('\n');
  let state = createParserState(0);
  state = pushChunk(state, lines.slice(0, 5).join('\n') + '\n', 1).state;
  const late = pushChunk(state, [lines[7], lines[6], lines[5]].join('\n') + '\n', 2);
  expect(late.accepted.map((event) => event.seq)).toEqual([5, 6, 7]);
  const reorder = pushChunk(late.state, lines[9] + '\n', 3);
  expect(reorder.accepted.map((event) => event.seq)).toEqual([9]);
  const straggler = pushChunk(reorder.state, lines[8] + '\n', 4);
  expect(straggler.state.stats.outOfOrder).toBe(1);
  expect(finishStream(straggler.state, 5).summary.events.map((event) => event.seq)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
});

test('sin final usa el chunk y marca la respuesta como degradada', () => {
  const summary = parseWholeStream(read('missing_final.ndjson'));
  expect(summary.final).toBeNull();
  expect(summary.degraded).toBe(true);
  expect(summary.chunkText).toBe('Respuesta final validada ñ 🦙');
  const cut = parseWholeStream(read('truncated_final.ndjson'));
  expect(cut.degraded).toBe(true);
  expect(cut.stats.invalid).toBe(1);
  expect(cut.missingDone).toBe(true);
});

test('un error terminal se informa con su código y si es reintentable, sin degradar', () => {
  const summary = parseWholeStream(read('error_event.ndjson'));
  expect(summary.error).toEqual({ code: 'TIMEOUT', retryable: true });
  expect(summary.degraded).toBe(false);
  expect(summary.incomplete).toBe(false);
});

test('los eventos antiguos sin v ni seq se aceptan; los de otra versión se descartan contados', () => {
  const legacy = parseWholeStream(read('legacy_no_seq.ndjson'));
  expect(legacy.stats).toMatchObject({ legacy: 2, valid: 2, invalid: 0 });
  expect(legacy.missingDone).toBe(false);
  const future = parseWholeStream(read('unsupported_version.ndjson'));
  expect(future.stats.unsupported).toBe(10);
  expect(future.incomplete).toBe(true);
  const oldError = parseWholeStream('{"type":"error","error":"Fallo sintético"}\n');
  expect(oldError.error).toEqual({ code: null, retryable: false });
});

test('extractObjects separa objetos pegados, ignora basura exterior y respeta las cadenas', () => {
  expect(extractObjects('data: {"a":1}{"b":"}{"}  ,')).toEqual(['{"a":1}', '{"b":"}{"}']);
  expect(extractObjects('{"a":')).toEqual([]);
  expect(extractObjects('sin llaves')).toEqual([]);
  expect(extractObjects('{"s":"\\"}"}')).toEqual(['{"s":"\\"}"}']);
});

test('un evento de otra petición no se mezcla con el resultado', () => {
  const summary = parseWholeStream(read('foreign_request_id.ndjson'));
  expect(summary.stats.invalid).toBe(1);
  expect(summary.events.every((event) => event.seq === null || (event as { request_id: string }).request_id === '0123456789abcdef0123456789abcdef')).toBe(true);
});

test('mide los tiempos con el reloj inyectado: primer byte, primer chunk, terminal, total y etapas', () => {
  const lines = read('valid.ndjson').trim().split('\n');
  let state = createParserState(100);
  state = pushChunk(state, lines.slice(0, 3).join('\n') + '\n', 130).state;
  state = pushChunk(state, lines.slice(3, 8).join('\n') + '\n', 400).state;
  state = pushChunk(state, lines.slice(8).join('\n') + '\n', 450).state;
  const { timings } = finishStream(state, 500).summary;
  expect(timings).toMatchObject({ firstByteMs: 30, firstChunkMs: 300, terminalMs: 350, totalMs: 400 });
  expect(timings.stageMs).toEqual({ retrieval: 100, generation: 150, validation: 40 });
  expect(summarise(createParserState(0), 10).timings).toMatchObject({ firstByteMs: null, firstChunkMs: null, terminalMs: null, totalMs: 10 });
});

test('la telemetría del cliente contiene solo números y el request_id, y nada de texto', () => {
  const summary = parseWholeStream(read('valid.ndjson'), 250);
  const payload = buildStreamTelemetry(summary, 'final');
  expect(payload).toMatchObject({ request_id: '0123456789abcdef0123456789abcdef', outcome: 'final', degraded: false, lines_valid: 10 });
  const serialised = JSON.stringify(payload);
  expect(serialised).not.toContain('Respuesta final');
  expect(serialised).not.toContain('Consulta');
  expect(Object.keys(payload ?? {}).sort()).toEqual(
    ['degraded', 'lines_duplicate', 'lines_invalid', 'lines_legacy', 'lines_out_of_order', 'lines_repaired', 'lines_valid', 'outcome', 'request_id', 'stage_ms', 'total_ms', 'ttfb_ms'].sort(),
  );
  expect(buildStreamTelemetry(parseWholeStream(read('legacy_no_seq.ndjson')), 'final')).toBeNull();
});

test('la telemetría usa sendBeacon con text/plain y nunca lanza ni envía sin datos', async () => {
  const sent: Array<{ url: string; body: Blob }> = [];
  const original = Object.getOwnPropertyDescriptor(navigator, 'sendBeacon');
  Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: (url: string, body: Blob) => { sent.push({ url, body }); return true; } });
  try {
    const payload = buildStreamTelemetry(parseWholeStream(read('valid.ndjson')), 'final');
    expect(sendStreamTelemetry('http://api.test', payload)).toBe(true);
    expect(sent[0].url).toBe('http://api.test/telemetry/stream');
    expect(sent[0].body.type).toContain('text/plain');
    expect(sendStreamTelemetry('http://api.test', null)).toBe(false);
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: () => { throw new Error('boom'); } });
    expect(sendStreamTelemetry('http://api.test', payload)).toBe(false);
  } finally {
    if (original) Object.defineProperty(navigator, 'sendBeacon', original);
    else delete (navigator as unknown as Record<string, unknown>).sendBeacon;
  }
});
