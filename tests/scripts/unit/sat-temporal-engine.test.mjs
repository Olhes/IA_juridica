import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const engine = require('../../../backend/static/sat-review/temporal-engine.js');

function shiftIso(iso, deltaMs) {
  const baseMs = engine.parseInstantMs(iso);
  return new Date(baseMs + deltaMs).toISOString();
}

function formatWithOffset(utcMs, offsetMinutes) {
  const local = new Date(utcMs + offsetMinutes * 60000);
  const pad2 = (n) => String(n).padStart(2, '0');
  const pad3 = (n) => String(n).padStart(3, '0');
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMinutes);
  const oh = pad2(Math.floor(abs / 60));
  const om = pad2(abs % 60);
  const frac = local.getUTCMilliseconds() ? '.' + pad3(local.getUTCMilliseconds()) : '';
  return (
    local.getUTCFullYear() +
    '-' + pad2(local.getUTCMonth() + 1) +
    '-' + pad2(local.getUTCDate()) +
    'T' + pad2(local.getUTCHours()) +
    ':' + pad2(local.getUTCMinutes()) +
    ':' + pad2(local.getUTCSeconds()) +
    frac +
    sign + oh + ':' + om
  );
}

const AMENDMENT_CHAIN_DATASET = {
  schemaVersion: 'sat-graph-viewer/1',
  source: 'bundled-sample',
  title: 'Peruvian Statutory Amendment Chain',
  items: [
    { id: 'norm:28970', typeId: 'norm', label: 'Ley 28970', parentId: null },
    { id: 'art:28970:1', typeId: 'article', label: 'Artículo 1', parentId: 'norm:28970' },
  ],
  versions: [
    {
      id: 'v1',
      itemId: 'art:28970:1',
      type: 'statutory',
      validityInterval: ['2007-01-27T00:00:00Z', '2018-09-12T00:00:00Z'],
      metadata: { legalIntervalKnown: true },
    },
    {
      id: 'v2',
      itemId: 'art:28970:1',
      type: 'statutory',
      validityInterval: ['2018-09-12T00:00:00Z', '2024-03-15T00:00:00Z'],
      metadata: { legalIntervalKnown: true },
    },
    {
      id: 'v3',
      itemId: 'art:28970:1',
      type: 'statutory',
      validityInterval: ['2024-03-15T00:00:00Z', null],
      metadata: { legalIntervalKnown: true },
    },
  ],
  actions: [
    {
      id: 'act-3',
      kind: 'amend',
      eventTime: '2024-03-15T00:00:00Z',
      terminatesVersionIds: ['v2'],
      producesVersionIds: ['v3'],
      label: 'Reforma 2024',
    },
    {
      id: 'act-1',
      kind: 'enact',
      eventTime: '2007-01-27T00:00:00Z',
      terminatesVersionIds: [],
      producesVersionIds: ['v1'],
      label: 'Promulgación 2007',
    },
    {
      id: 'act-2',
      kind: 'amend',
      eventTime: '2018-09-12T00:00:00Z',
      terminatesVersionIds: ['v1'],
      producesVersionIds: ['v2'],
      label: 'Reforma DL 1377',
    },
  ],
  textUnits: [
    { id: 'tu1', sourceType: 'Version', sourceId: 'v1', language: 'es', aspect: 'canonical', content: 'Texto v1' },
    { id: 'tu2', sourceType: 'Version', sourceId: 'v2', language: 'es', aspect: 'canonical', content: 'Texto v2' },
    { id: 'tu3', sourceType: 'Version', sourceId: 'v3', language: 'es', aspect: 'canonical', content: 'Texto v3' },
  ],
};

const INTERPRETIVE_OVERLAY_DATASET = {
  schemaVersion: 'sat-graph-viewer/1',
  source: 'bundled-sample',
  title: 'Statutory + Interpretive Concurrent Overlay',
  items: [
    { id: 'norm:30364', typeId: 'norm', label: 'Ley 30364', parentId: null },
    { id: 'art:30364:16', typeId: 'article', label: 'Artículo 16', parentId: 'norm:30364' },
  ],
  versions: [
    {
      id: 'stv-1',
      itemId: 'art:30364:16',
      type: 'statutory',
      validityInterval: ['2015-11-23T00:00:00Z', null],
      metadata: { legalIntervalKnown: true },
    },
    {
      id: 'itv-1',
      itemId: 'art:30364:16',
      type: 'interpretive',
      validityInterval: ['2019-09-10T00:00:00Z', '2023-06-01T00:00:00Z'],
      metadata: { legalIntervalKnown: true },
    },
    {
      id: 'itv-2',
      itemId: 'art:30364:16',
      type: 'interpretive',
      validityInterval: ['2021-11-18T00:00:00Z', null],
      metadata: { legalIntervalKnown: true },
    },
  ],
  actions: [
    {
      id: 'act-enact',
      kind: 'enact',
      eventTime: '2015-11-23T00:00:00Z',
      terminatesVersionIds: [],
      producesVersionIds: ['stv-1'],
    },
    {
      id: 'act-interp-1',
      kind: 'interpret',
      eventTime: '2019-09-10T00:00:00Z',
      terminatesVersionIds: [],
      producesVersionIds: ['itv-1'],
    },
    {
      id: 'act-interp-2',
      kind: 'interpret',
      eventTime: '2021-11-18T00:00:00Z',
      terminatesVersionIds: [],
      producesVersionIds: ['itv-2'],
    },
  ],
  textUnits: [
    { id: 'tu-s', sourceType: 'Version', sourceId: 'stv-1', language: 'es', aspect: 'canonical', content: 'Norma base' },
    { id: 'tu-i1', sourceType: 'Version', sourceId: 'itv-1', language: 'es', aspect: 'holding', content: 'Criterio 1' },
    { id: 'tu-i2', sourceType: 'Version', sourceId: 'itv-2', language: 'es', aspect: 'ratio', content: 'Criterio 2' },
  ],
};

test('parseQueryInstant accepts YYYY-MM-DD and strict RFC 3339 with offsets, and rejects invalid inputs', () => {
  const d = engine.parseQueryInstant('2025-01-01');
  assert.ok(d instanceof Date);
  assert.equal(d.toISOString(), '2025-01-01T00:00:00.000Z');
  assert.equal(engine.normalizeInstantISO('2025-01-01'), '2025-01-01T00:00:00Z');
  assert.equal(engine.normalizeInstantISO('2025-01-01T00:00:00.001Z'), '2025-01-01T00:00:00.001Z');

  // Equivalent instants across timezone offsets must yield exact same epoch ms.
  const utcMs = engine.parseInstantMs('2024-03-15T00:00:00Z');
  assert.equal(engine.parseInstantMs('2024-03-14T19:00:00-05:00'), utcMs);
  assert.equal(engine.parseInstantMs('2024-03-15T05:00:00+05:00'), utcMs);
  assert.equal(engine.parseInstantMs('2024-03-15'), utcMs);

  // Valid leap dates.
  assert.equal(engine.normalizeInstantISO('2024-02-29'), '2024-02-29T00:00:00Z');
  assert.equal(engine.normalizeInstantISO('2000-02-29'), '2000-02-29T00:00:00Z');

  const invalidInputs = [
    '',
    '   ',
    null,
    undefined,
    1234567890,
    '2025-01-01T12:00:00',       // offset-less datetime
    '2025-01-01 12:00:00Z',      // space separator
    '2025-02-29',                // non-leap year Feb 29
    '2019-02-30',                // impossible Feb 30
    '1900-02-29',                // century non-leap year
    '2024-04-31T00:00:00Z',      // April 31
    '2024-13-01T00:00:00Z',      // month 13
    '2024-01-01T24:00:00Z',      // hour 24
    '2024-01-01T12:60:00Z',      // minute 60
    '2024-01-01T12:00:00+25:00', // invalid offset hour
    ' 2024-01-01',               // leading whitespace
  ];

  for (const bad of invalidInputs) {
    assert.throws(
      () => engine.parseQueryInstant(bad),
      TypeError,
      `Expected TypeError for invalid instant: ${String(bad)}`,
    );
  }
});

test('automated +/-1ms and +/-1s boundary matrix proves strict half-open [start, end) non-overlap on statutory chain', () => {
  const transitions = [
    {
      at: '2007-01-27T00:00:00Z',
      before: [],
      exact: ['v1'],
      after: ['v1'],
    },
    {
      at: '2018-09-12T00:00:00Z',
      before: ['v1'],
      exact: ['v2'],
      after: ['v2'],
    },
    {
      at: '2024-03-15T00:00:00Z',
      before: ['v2'],
      exact: ['v3'],
      after: ['v3'],
    },
  ];

  const probes = [
    { label: 't - 1s', deltaMs: -1000, bucket: 'before' },
    { label: 't - 1ms', deltaMs: -1, bucket: 'before' },
    { label: 't', deltaMs: 0, bucket: 'exact' },
    { label: 't + 1ms', deltaMs: 1, bucket: 'after' },
    { label: 't + 1s', deltaMs: 1000, bucket: 'after' },
  ];

  for (const transition of transitions) {
    for (const probe of probes) {
      const targetIso = shiftIso(transition.at, probe.deltaMs);
      const targetMs = engine.parseInstantMs(targetIso);
      const representations = [
        targetIso,
        formatWithOffset(targetMs, 300),   // +05:00
        formatWithOffset(targetMs, -300),  // -05:00
      ];

      for (const repr of representations) {
        const valid = engine.getValidVersions(AMENDMENT_CHAIN_DATASET, repr, { itemId: 'art:28970:1' });
        const ids = valid.map((v) => v.id);
        assert.deepEqual(
          ids,
          transition[probe.bucket],
          `Mismatch at ${transition.at} (${probe.label}, repr=${repr})`,
        );
        // Statutory non-overlap invariant: at most one statutory version active at any instant.
        assert.ok(ids.length <= 1);
      }
    }
  }
});

test('automated +/-1ms and +/-1s boundary matrix confirms concurrent S-TV + I-TV interpretive overlays', () => {
  const transitions = [
    {
      at: '2015-11-23T00:00:00Z',
      before: [],
      exact: ['stv-1'],
      after: ['stv-1'],
    },
    {
      at: '2019-09-10T00:00:00Z',
      before: ['stv-1'],
      exact: ['stv-1', 'itv-1'],
      after: ['stv-1', 'itv-1'],
    },
    {
      at: '2021-11-18T00:00:00Z',
      before: ['stv-1', 'itv-1'],
      exact: ['stv-1', 'itv-1', 'itv-2'],
      after: ['stv-1', 'itv-1', 'itv-2'],
    },
    {
      at: '2023-06-01T00:00:00Z',
      before: ['stv-1', 'itv-1', 'itv-2'],
      exact: ['stv-1', 'itv-2'],
      after: ['stv-1', 'itv-2'],
    },
  ];

  for (const tr of transitions) {
    for (const [deltaMs, bucket] of [[-1000, 'before'], [-1, 'before'], [0, 'exact'], [1, 'after'], [1000, 'after']]) {
      const iso = shiftIso(tr.at, deltaMs);
      const ids = engine
        .getValidVersions(INTERPRETIVE_OVERLAY_DATASET, iso, { itemId: 'art:30364:16' })
        .map((v) => v.id);
      assert.deepEqual(ids, tr[bucket], `Overlay mismatch at ${tr.at} delta=${deltaMs}ms`);
    }
  }

  // Filter by version type separates statutory from interpretive cleanly.
  const atPeak = '2022-01-01T00:00:00Z';
  assert.deepEqual(
    engine.getValidVersions(INTERPRETIVE_OVERLAY_DATASET, atPeak, { type: 'statutory' }).map((v) => v.id),
    ['stv-1'],
  );
  assert.deepEqual(
    engine.getValidVersions(INTERPRETIVE_OVERLAY_DATASET, atPeak, { type: 'interpretive' }).map((v) => v.id),
    ['itv-1', 'itv-2'],
  );
});

test('getItemHistory orders actions deterministically by (eventTime, id) with null timestamps last', () => {
  const dataset = {
    items: [{ id: 'art-1', typeId: 'article', label: 'Art 1' }],
    versions: [
      { id: 'v1', itemId: 'art-1', type: 'statutory', validityInterval: ['2020-01-01T00:00:00Z', '2022-01-01T00:00:00Z'] },
      { id: 'v2', itemId: 'art-1', type: 'statutory', validityInterval: ['2022-01-01T00:00:00Z', null] },
    ],
    actions: [
      { id: 'a-null-b', kind: 'amend_reference', eventTime: null, producesVersionIds: ['v2'] },
      { id: 'a-tied-z', kind: 'amend', eventTime: '2022-01-01T00:00:00Z', terminatesVersionIds: ['v1'], producesVersionIds: ['v2'] },
      { id: 'a-tied-a', kind: 'interpret', eventTime: '2022-01-01T05:00:00+05:00', producesVersionIds: ['v2'] },
      { id: 'a-null-a', kind: 'amend_reference', eventTime: null, producesVersionIds: ['v1'] },
      { id: 'a-first', kind: 'enact', eventTime: '2020-01-01T00:00:00Z', producesVersionIds: ['v1'] },
    ],
  };

  const history = engine.getItemHistory(dataset, 'art-1');
  assert.deepEqual(
    history.map((a) => a.id),
    ['a-first', 'a-tied-a', 'a-tied-z', 'a-null-a', 'a-null-b'],
  );
});

test('[null, null] unknown intervals are excluded by default and included only when includeUnknownSnapshots is true', () => {
  const snapshotDataset = {
    items: [{ id: 'art-snap', typeId: 'article', label: 'Art Snapshot' }],
    versions: [
      {
        id: 'v-snap',
        itemId: 'art-snap',
        type: 'statutory',
        validityInterval: [null, null],
        metadata: { legalIntervalKnown: false, snapshotAsOf: '2026-11-12T00:00:00Z' },
      },
    ],
    actions: [],
    textUnits: [],
  };

  assert.equal(engine.isInHalfOpenInterval(engine.parseInstantMs('2026-11-12'), [null, null]), false);
  assert.equal(
    engine.isInHalfOpenInterval(engine.parseInstantMs('2026-11-12'), [null, null], { includeUnknownSnapshots: true }),
    true,
  );
  assert.deepEqual(engine.getValidVersions(snapshotDataset, '2026-11-12'), []);
  assert.deepEqual(
    engine.getValidVersions(snapshotDataset, '2026-11-12', { includeUnknownSnapshots: true }).map((v) => v.id),
    ['v-snap'],
  );
});

test('normalizeDataset handles upstream JSON aliases non-destructively and lifts inline version text', () => {
  const rawUpstream = Object.freeze({
    title: 'Upstream Viewer JSON',
    items: Object.freeze([
      Object.freeze({ id: 'item-1', type: 'article', title: 'Article 1' }),
    ]),
    versions: Object.freeze([
      Object.freeze({
        id: 'ver-1',
        itemId: 'item-1',
        type: 'statutory',
        validity: Object.freeze({ start: '2021-01-01T00:00:00Z', end: '2022-01-01T00:00:00Z' }),
        content: 'Initial statutory wording.',
        language: 'en',
      }),
      Object.freeze({
        id: 'ver-2',
        itemId: 'item-1',
        type: 'statutory',
        validFrom: '2022-01-01T00:00:00Z',
        validTo: null,
        text: 'Amended statutory wording.',
        language: 'en',
      }),
    ]),
    actions: Object.freeze([
      Object.freeze({
        id: 'act-1',
        type: 'amend',
        effectiveTime: '2022-01-01T00:00:00Z',
        terminates: Object.freeze(['ver-1']),
        produces: Object.freeze(['ver-2']),
      }),
    ]),
  });

  const normalized = engine.normalizeDataset(rawUpstream);
  assert.equal(normalized.items[0].typeId, 'article');
  assert.equal(normalized.items[0].label, 'Article 1');
  assert.deepEqual(normalized.versions[0].validityInterval, ['2021-01-01T00:00:00Z', '2022-01-01T00:00:00Z']);
  assert.deepEqual(normalized.versions[1].validityInterval, ['2022-01-01T00:00:00Z', null]);
  assert.equal(normalized.actions[0].kind, 'amend');
  assert.equal(normalized.actions[0].eventTime, '2022-01-01T00:00:00Z');
  assert.deepEqual(normalized.actions[0].terminatesVersionIds, ['ver-1']);
  assert.deepEqual(normalized.actions[0].producesVersionIds, ['ver-2']);
  assert.equal(normalized.textUnits.length, 2);
  assert.equal(normalized.textUnits[0].sourceId, 'ver-1');
  assert.equal(normalized.textUnits[0].content, 'Initial statutory wording.');
  assert.equal(normalized.textUnits[1].sourceId, 'ver-2');
  assert.equal(normalized.textUnits[1].content, 'Amended statutory wording.');

  // Upstream dataset works seamlessly with getValidVersions and validateDataset.
  assert.equal(engine.validateDataset(rawUpstream).valid, true);
  assert.deepEqual(engine.getValidVersions(rawUpstream, '2021-12-31T23:59:59.999Z').map((v) => v.id), ['ver-1']);
  assert.deepEqual(engine.getValidVersions(rawUpstream, '2022-01-01T00:00:00Z').map((v) => v.id), ['ver-2']);
});

test('validateDataset reports structural, temporal, and statutory-overlap defects while allowing interpretive overlap', () => {
  const chainReport = engine.validateDataset(AMENDMENT_CHAIN_DATASET);
  assert.equal(chainReport.valid, true);
  assert.equal(chainReport.errors.length, 0);
  assert.deepEqual(chainReport.stats, { items: 2, versions: 3, actions: 3, textUnits: 3 });

  const overlayReport = engine.validateDataset(INTERPRETIVE_OVERLAY_DATASET);
  assert.equal(overlayReport.valid, true);
  assert.equal(overlayReport.errors.length, 0);

  const broken = {
    items: [{ id: 'a1', typeId: 'article', label: 'A1', parentId: 'missing-parent' }],
    versions: [
      { id: 'v1', itemId: 'a1', type: 'statutory', validityInterval: ['2020-01-01T00:00:00Z', '2022-06-01T00:00:00Z'] },
      { id: 'v2', itemId: 'a1', type: 'statutory', validityInterval: ['2022-01-01T00:00:00Z', '2021-01-01T00:00:00Z'] },
      { id: 'v3', itemId: 'missing-item', type: 'statutory', validityInterval: ['2022-01-01T10:00:00', null] },
    ],
    actions: [
      { id: 'act-bad', kind: 'amend', eventTime: '2022-01-01T00:00:00Z', terminatesVersionIds: ['v1'], producesVersionIds: ['v2', 'missing-v'] },
    ],
    textUnits: [
      { id: 'tu-bad', sourceType: 'Version', sourceId: 'missing-v', language: 'es', aspect: 'canonical', content: 'x' },
    ],
  };

  const report = engine.validateDataset(broken);
  assert.equal(report.valid, false);
  const codes = new Set(report.errors.map((e) => e.code));
  assert.ok(codes.has('BROKEN_ITEM_PARENT'));
  assert.ok(codes.has('INVERTED_INTERVAL'));
  assert.ok(codes.has('BROKEN_VERSION_ITEM'));
  assert.ok(codes.has('INVALID_VERSION_INSTANT'));
  assert.ok(codes.has('BROKEN_ACTION_VERSION'));
  assert.ok(codes.has('BROKEN_TEXT_UNIT_SOURCE'));

  // Statutory overlap detection on valid non-inverted intervals.
  const overlappingStatutory = {
    items: [{ id: 'a1', typeId: 'article', label: 'A1' }],
    versions: [
      { id: 'v1', itemId: 'a1', type: 'statutory', validityInterval: ['2020-01-01T00:00:00Z', '2023-01-01T00:00:00Z'] },
      { id: 'v2', itemId: 'a1', type: 'statutory', validityInterval: ['2022-01-01T00:00:00Z', null] },
    ],
    actions: [
      { id: 'act-ov', kind: 'amend', eventTime: '2022-01-01T00:00:00Z', terminatesVersionIds: ['v1'], producesVersionIds: ['v2'] },
    ],
    textUnits: [],
  };
  const overlapReport = engine.validateDataset(overlappingStatutory);
  assert.equal(overlapReport.valid, false);
  assert.ok(overlapReport.errors.some((e) => e.code === 'STATUTORY_OVERLAP'));
  assert.ok(overlapReport.errors.some((e) => e.code === 'SUPERSESSION_OVERLAP'));
});

test('collectTimelineTicks and diffVersionTexts produce deterministic sorted ticks and lossless diffs', () => {
  const ticks = engine.collectTimelineTicks(AMENDMENT_CHAIN_DATASET);
  assert.deepEqual(
    ticks.map((t) => t.iso),
    ['2007-01-27T00:00:00Z', '2018-09-12T00:00:00Z', '2024-03-15T00:00:00Z'],
  );
  assert.ok(ticks[1].kinds.includes('version_end'));
  assert.ok(ticks[1].kinds.includes('version_start'));
  assert.ok(ticks[1].kinds.includes('amend'));

  const before = 'Artículo 1. El juez dicta medidas en plazo de 72 horas.\nSe notifica al interesado.';
  const after = 'Artículo 1. El juzgado de familia dicta medidas inmediatas en plazo de 24 horas.\nSe notifica al interesado.';
  const ops = engine.diffVersionTexts(before, after);
  assert.ok(ops.some((o) => o.op === 'delete'));
  assert.ok(ops.some((o) => o.op === 'insert'));
  assert.ok(ops.some((o) => o.op === 'equal'));

  const rebuiltBefore = ops.filter((o) => o.op !== 'insert').map((o) => o.text).join('');
  const rebuiltAfter = ops.filter((o) => o.op !== 'delete').map((o) => o.text).join('');
  assert.equal(rebuiltBefore, before);
  assert.equal(rebuiltAfter, after);

  assert.deepEqual(engine.diffVersionTexts('igual', 'igual'), [{ op: 'equal', text: 'igual' }]);
  assert.deepEqual(engine.diffVersionTexts('', 'nuevo'), [{ op: 'insert', text: 'nuevo' }]);
  assert.deepEqual(engine.diffVersionTexts('borrado', ''), [{ op: 'delete', text: 'borrado' }]);
  assert.deepEqual(engine.diffVersionTexts('', ''), []);
});
