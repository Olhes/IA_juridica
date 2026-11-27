import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {JSDOM} from 'jsdom';

const ASSETS = new URL('../../../backend/static/sat-review/', import.meta.url);

function loadWorkstation(fixture, fetchImpl) {
  const html = readFileSync(new URL('index.html', ASSETS), 'utf8');
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'http://localhost:8011/sat-graph/review',
  });
  const {window} = dom;
  window.structuredClone = structuredClone;
  window.HTMLDialogElement.prototype.showModal = function () {this.open = true;};
  window.HTMLDialogElement.prototype.close = function () {this.open = false;};
  window.Element.prototype.scrollIntoView = function () {};
  window.fetch = fetchImpl || (async () => ({ok: true, json: async () => ({})}));
  window.fixture = fixture;

  window.eval(readFileSync(new URL('temporal-engine.js', ASSETS), 'utf8'));
  const editorSrc = readFileSync(new URL('editor.js', ASSETS), 'utf8');
  assert.match(editorSrc, /\bconnect\(\);\s*$/u, 'editor.js must keep connect(); as its final line');
  window.eval(
    editorSrc.replace(
      /\bconnect\(\);\s*$/u,
      'window.loadFixture = pos => showDocument(window.fixture, pos);',
    ),
  );
  window.eval(readFileSync(new URL('graphragprov.js', ASSETS), 'utf8'));
  window.eval(readFileSync(new URL('temporal-viewer.js', ASSETS), 'utf8'));
  window.loadFixture();
  return {dom, window, html};
}

function makeBaseFixture() {
  const markdown = 'Norma 😀\nArtículo 1. El Poder Judicial ñ deberá registrar <script>window.__xss=1</script> en el REDAM.\n';
  const cpLen = s => Array.from(s).length;
  const artStart = cpLen(markdown.slice(0, markdown.indexOf('Artículo 1.')));
  const totalCp = cpLen(markdown);
  return {
    id: 'pe:ley:28970',
    title: 'Ley N° 28970',
    editable: true,
    history: [],
    components: 2,
    retrievable: 1,
    versions: [
      {
        id: 'v-art1',
        work_id: 'w-art1',
        component_id: 'art1',
        label: 'Artículo 1',
        retrievable: true,
        archived: false,
        provenance: 'user_attested_snapshot',
        texts: [{id: 't-art1', language: 'es'}],
      },
    ],
    edition: {
      revision: 'rev-1',
      markdown,
      components: [
        {id: 'root', label: 'Norma', kind: 'document', parent_id: null, start: 0, end: totalCp},
        {id: 'art1', label: 'Artículo 1', kind: 'article', parent_id: 'root', start: artStart, end: totalCp},
      ],
    },
  };
}

function flushAsync() {
  return new Promise(resolve => setTimeout(resolve, 25));
}

test('tab switching hides inspector on provenance/temporal tabs and restores user state on structure', async () => {
  const {window, html} = loadWorkstation(makeBaseFixture(), async url => {
    if (url.endsWith('/provenance/capabilities')) {
      return {ok: true, json: async () => ({offline_ready: true, cohere_available: false, templates: []})};
    }
    if (url.endsWith('/provenance-graph')) {
      return {
        ok: true,
        json: async () => ({
          doc_id: 'pe:ley:28970',
          occurrences: [],
          predicates: [],
          source_units: {},
          sample_queries: [],
          subgraph: {nodes: [], edges: []},
          stats: {units: 0, occurrences: 0, predicates: 0, unlocalized_discarded: 0},
        }),
      };
    }
    if (url.includes('/temporal/dataset')) {
      return {
        ok: true,
        json: async () => ({
          schemaVersion: 'sat-graph-viewer/1',
          source: 'live-corpus',
          title: 'Ley N° 28970',
          policyNote: 'Policy',
          items: [],
          versions: [],
          actions: [],
          textUnits: [],
        }),
      };
    }
    return {ok: true, json: async () => ({})};
  });

  try {
    const $ = id => window.document.getElementById(id);

    // CSP markup guarantees: zero inline scripts, zero style tags, zero inline style attributes.
    assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/i);
    assert.doesNotMatch(html, /<style[\s>]/i);
    assert.doesNotMatch(html, /\sstyle\s*=/i);

    // New tabs do not set aria-controls per modern-web-guidance tabs pattern.
    assert.equal($('tab-provenance').hasAttribute('aria-controls'), false);
    assert.equal($('tab-temporal').hasAttribute('aria-controls'), false);

    // Inspector starts visible on structure tab.
    assert.equal($('component-inspector').hidden, false);
    assert.equal($('structure-view').hidden, false);

    // Switch to provenance -> inspector auto-hides.
    $('tab-provenance').click();
    await flushAsync();
    assert.equal($('provenance-view').hidden, false);
    assert.equal($('structure-view').hidden, true);
    assert.equal($('component-inspector').hidden, true);
    assert.equal($('review-grid').classList.contains('inspector-collapsed'), true);

    // Return to structure -> inspector restores visible.
    window.document.querySelector('[data-tab="structure"]').click();
    assert.equal($('structure-view').hidden, false);
    assert.equal($('provenance-view').hidden, true);
    assert.equal($('component-inspector').hidden, false);

    // User manually collapses inspector -> switching to temporal and back keeps it collapsed.
    $('toggle-inspector').click();
    assert.equal($('component-inspector').hidden, true);
    $('tab-temporal').click();
    await flushAsync();
    assert.equal($('temporal-view').hidden, false);
    assert.equal($('component-inspector').hidden, true);
    window.document.querySelector('[data-tab="structure"]').click();
    assert.equal($('component-inspector').hidden, true);
  } finally {
    window.close();
  }
});

test('GraphRAGProv renders exact Unicode non-BMP <mark> spans safely and syncs 3-way highlighting', async () => {
  const fixture = makeBaseFixture();
  const unitText = 'Artículo 1. 😀 El Poder Judicial ñ deberá registrar <script>window.__xss=1</script> en el REDAM.';
  const cpIndex = (str, needle) => Array.from(str.slice(0, str.indexOf(needle))).length;
  const cpLen = str => Array.from(str).length;
  const baseOffset = 9; // "Norma 😀\n" is 8 codepoints; arbitrary non-zero component_start_in_doc

  const subjText = 'Poder Judicial ñ';
  const predText = 'deberá registrar';
  const objText = '<script>window.__xss=1</script>';
  const obj2Text = 'REDAM';

  const subjStart = cpIndex(unitText, subjText);
  const predStart = cpIndex(unitText, predText);
  const objStart = cpIndex(unitText, objText);
  const obj2Start = cpIndex(unitText, obj2Text);

  const occA = {
    token: 'occ_aaaaaaaaaaaa',
    doc_id: 'pe:ley:28970',
    passage_id: 'art1',
    subject: {kind: 'iri', value: 'http://iajuridica.pe/entity/pj', label: subjText},
    predicate: {kind: 'iri', value: 'http://iajuridica.pe/legal/obligates', label: 'obligates'},
    object: {kind: 'literal', value: objText, label: objText},
    origin: 'deterministic_legal',
    confidence_rule: 'deontic',
    spans: {
      component_id: 'art1',
      component_start_in_doc: baseOffset,
      evidence_span: {start: 0, end: cpLen(unitText), surface_text: unitText, quality: 'exact'},
      doc_evidence_span: {start: baseOffset, end: baseOffset + cpLen(unitText), surface_text: unitText, quality: 'exact'},
      subject_span: {start: baseOffset + subjStart, end: baseOffset + subjStart + cpLen(subjText), surface_text: subjText, quality: 'exact'},
      predicate_span: {start: baseOffset + predStart, end: baseOffset + predStart + cpLen(predText), surface_text: predText, quality: 'exact'},
      object_span: {start: baseOffset + objStart, end: baseOffset + objStart + cpLen(objText), surface_text: objText, quality: 'exact'},
    },
  };

  const occB = {
    token: 'occ_bbbbbbbbbbbb',
    doc_id: 'pe:ley:28970',
    passage_id: 'art1',
    subject: {kind: 'iri', value: 'http://iajuridica.pe/entity/pj', label: subjText},
    predicate: {kind: 'iri', value: 'http://iajuridica.pe/legal/administers', label: 'administers'},
    object: {kind: 'literal', value: obj2Text, label: obj2Text},
    origin: 'deterministic_legal',
    confidence_rule: 'deontic',
    spans: {
      component_id: 'art1',
      component_start_in_doc: baseOffset,
      evidence_span: {start: 0, end: cpLen(unitText), surface_text: unitText, quality: 'exact'},
      doc_evidence_span: {start: baseOffset, end: baseOffset + cpLen(unitText), surface_text: unitText, quality: 'exact'},
      subject_span: {start: baseOffset + subjStart, end: baseOffset + subjStart + cpLen(subjText), surface_text: subjText, quality: 'exact'},
      predicate_span: null,
      object_span: {start: baseOffset + obj2Start, end: baseOffset + obj2Start + cpLen(obj2Text), surface_text: obj2Text, quality: 'exact'},
    },
  };

  const graphDto = {
    doc_id: 'pe:ley:28970',
    revision: 'rev-1',
    source_kind: 'published',
    occurrences: [occA, occB],
    predicates: ['obligates', 'administers'],
    cohere_used: false,
    unlocalized_discarded: 0,
    sample_queries: [
      {
        id: 'sq1',
        title: 'Obligaciones (Join ⊗)',
        question: '¿Qué debe registrar el Poder Judicial?',
        sparql: 'SELECT ?s ?o WHERE { ?s <http://iajuridica.pe/legal/obligates> ?o . }',
        highlights_algebra: 'Conjunción ⊗',
      },
    ],
    source_units: {
      art1: {
        id: 'art1',
        label: 'Artículo 1',
        kind: 'article',
        text: unitText,
        global_start: baseOffset,
        global_end: baseOffset + cpLen(unitText),
      },
    },
    subgraph: {
      nodes: [
        {id: 'iri:pj', label: subjText, kind: 'iri', value: 'http://iajuridica.pe/entity/pj'},
        {id: 'lit:1', label: objText, kind: 'literal', value: objText},
        {id: 'lit:2', label: obj2Text, kind: 'literal', value: obj2Text},
      ],
      edges: [
        {token: 'occ_aaaaaaaaaaaa', source: 'iri:pj', target: 'lit:1', predicate: 'obligates', parallel_index: 0, parallel_count: 1},
        {token: 'occ_bbbbbbbbbbbb', source: 'iri:pj', target: 'lit:2', predicate: 'administers', parallel_index: 0, parallel_count: 1},
      ],
    },
    stats: {units: 1, occurrences: 2, predicates: 2, unlocalized_discarded: 0},
  };

  const queryDto = {
    doc_id: 'pe:ley:28970',
    revision: 'rev-1',
    sparql: graphDto.sample_queries[0].sparql,
    nl_compiler: 'none',
    variables: ['s', 'o'],
    rows: [
      {
        row_index: 0,
        bindings: {s: occA.subject, o: occA.object},
        polynomial: 'occ_aaaaaaaaaaaa ⊗ occ_bbbbbbbbbbbb',
        compact_polynomial: 'occ_aaaaaaaaaaaa ⊗ occ_bbbbbbbbbbbb',
        npcs_prefix: '(* occ_aaaaaaaaaaaa occ_bbbbbbbbbbbb)',
        monomials: [
          {coeff: 1, factors: [{token: 'occ_aaaaaaaaaaaa', exp: 1}, {token: 'occ_bbbbbbbbbbbb', exp: 1}]},
        ],
        witness_count: 1,
        occurrence_tokens: ['occ_aaaaaaaaaaaa', 'occ_bbbbbbbbbbbb'],
        truncated: false,
      },
    ],
    occurrences: {occ_aaaaaaaaaaaa: occA, occ_bbbbbbbbbbbb: occB},
    source_units: graphDto.source_units,
    subgraph: graphDto.subgraph,
    execution_ms: 1.4,
    warnings: [],
  };

  const {window} = loadWorkstation(fixture, async (url) => {
    if (url.endsWith('/provenance/capabilities')) {
      return {ok: true, json: async () => ({offline_ready: true, cohere_available: false, templates: []})};
    }
    if (url.endsWith('/provenance-graph')) {
      return {ok: true, json: async () => graphDto};
    }
    if (url.endsWith('/provenance-query')) {
      return {ok: true, json: async () => queryDto};
    }
    return {ok: true, json: async () => ({})};
  });

  try {
    const $ = id => window.document.getElementById(id);
    $('tab-provenance').click();
    await flushAsync();

    // Cohere options are disabled when cohere_available is false.
    const cohereExtOpt = $('prov-extraction-mode').querySelector('option[value="hybrid_cohere"]');
    const cohereNlOpt = $('prov-nl-mode').querySelector('option[value="cohere"]');
    assert.equal(cohereExtOpt.disabled, true);
    assert.equal(cohereNlOpt.disabled, true);

    // XSS payload must be rendered strictly as text inside <mark>, never as <script> DOM.
    assert.equal($('prov-passage').querySelectorAll('script').length, 0);
    assert.equal(window.__xss, undefined);

    // Exact Unicode non-BMP slicing: subject and object <mark> texts match surface_text verbatim.
    const marks = Array.from($('prov-passage').querySelectorAll('mark.prov-mark'));
    const subjectMark = marks.find(m => m.dataset.role === 'subject');
    const objectScriptMark = marks.find(m => m.dataset.role === 'object' && m.textContent.includes('<script>'));
    const objectRedamMark = marks.find(m => m.dataset.role === 'object' && m.textContent === 'REDAM');
    assert.equal(subjectMark?.textContent, subjText);
    assert.equal(objectScriptMark?.textContent, objText);
    assert.equal(objectRedamMark?.textContent, obj2Text);

    // Clicking a multi-factor monomial button highlights BOTH SVG edges and active <mark> elements.
    const monomialBtn = $('prov-results-table').querySelector('.prov-monomial-btn');
    assert.ok(monomialBtn, 'Monomial conjunction button should exist');
    monomialBtn.click();
    const edgeA = $('prov-graph-svg').querySelector('.prov-svg-edge[data-token="occ_aaaaaaaaaaaa"]');
    const edgeB = $('prov-graph-svg').querySelector('.prov-svg-edge[data-token="occ_bbbbbbbbbbbb"]');
    assert.equal(edgeA.classList.contains('prov-active'), true);
    assert.equal(edgeB.classList.contains('prov-active'), true);
    assert.ok($('prov-passage').querySelectorAll('mark.prov-mark-active').length >= 2);

    // Clicking a specific <mark> (REDAM -> occ_bbbbbbbbbbbb only) syncs SVG edge + polynomial chip!
    const refreshedRedamMark = Array.from($('prov-passage').querySelectorAll('mark.prov-mark'))
      .find(m => m.textContent === 'REDAM');
    refreshedRedamMark.click();
    assert.equal(edgeA.classList.contains('prov-active'), false);
    assert.equal(edgeB.classList.contains('prov-active'), true);
    const chipA = $('prov-results-table').querySelector('.prov-token-chip[data-token="occ_aaaaaaaaaaaa"]');
    const chipB = $('prov-results-table').querySelector('.prov-token-chip[data-token="occ_bbbbbbbbbbbb"]');
    assert.equal(chipA.classList.contains('prov-active'), false);
    assert.equal(chipB.classList.contains('prov-active'), true);

    // NPCS prefix toggle reveals the prefix code block.
    $('prov-npcs-toggle').click();
    assert.equal(
      $('prov-results-table').querySelector('.prov-npcs-code')?.textContent,
      '(* occ_aaaaaaaaaaaa occ_bbbbbbbbbbbb)',
    );

    // Jump to Structure switches back to structure tab and selects art1.
    $('prov-jump-structure-btn').click();
    await flushAsync();
    assert.equal($('structure-view').hidden, false);
    assert.equal(window.SATReviewBridge.getContext().selectedComponentId, 'art1');
  } finally {
    window.close();
  }
});

test('Temporal Viewer syncs slider aria-valuetext & CSS vars, handles [null, null] toggle, diff, and JSON upload', async () => {
  const dataset = {
    schemaVersion: 'sat-graph-viewer/1',
    source: 'live-corpus',
    resourceId: 'pe:ley:28970',
    title: 'Ley N° 28970 · Prueba temporal',
    policyNote: 'Versiones [null, null] no sintetizan fechas legales.',
    items: [
      {id: 'item:norm', typeId: 'norm', label: 'Ley N° 28970', parentId: null},
      {id: 'item:art1', typeId: 'article', label: 'Artículo 1', parentId: 'item:norm'},
    ],
    versions: [
      {id: 'v1', itemId: 'item:art1', type: 'statutory', validityInterval: ['2010-01-01T00:00:00Z', '2020-01-01T00:00:00Z'], metadata: {legalIntervalKnown: true}},
      {id: 'v2', itemId: 'item:art1', type: 'statutory', validityInterval: ['2020-01-01T00:00:00Z', null], metadata: {legalIntervalKnown: true}},
      {id: 'itv1', itemId: 'item:art1', type: 'interpretive', validityInterval: ['2019-06-01T00:00:00Z', null], metadata: {legalIntervalKnown: true, authority: 'Corte Suprema'}},
      {id: 'snap1', itemId: 'item:art1', type: 'statutory', validityInterval: [null, null], metadata: {legalIntervalKnown: false}},
    ],
    actions: [
      {
        id: 'act:amend',
        kind: 'amend',
        eventTime: '2020-01-01T00:00:00Z',
        terminatesVersionIds: ['v1'],
        producesVersionIds: ['v2'],
        label: 'Reforma 2020',
      },
    ],
    textUnits: [
      {id: 'tu:v1', sourceId: 'v1', language: 'es', content: 'Artículo 1 texto original antiguo.'},
      {id: 'tu:v2', sourceId: 'v2', language: 'es', content: 'Artículo 1 texto reformado moderno.'},
      {id: 'tu:itv1', sourceId: 'itv1', language: 'es', content: 'Criterio interpretativo vinculante.'},
      {id: 'tu:snap1', sourceId: 'snap1', language: 'es', content: 'Captura editorial sin fecha legal.'},
    ],
  };

  const {window} = loadWorkstation(makeBaseFixture(), async url => {
    if (url.includes('/temporal/dataset/')) {
      return {ok: true, json: async () => dataset};
    }
    return {ok: true, json: async () => ({})};
  });

  try {
    const $ = id => window.document.getElementById(id);
    $('tab-temporal').click();
    await flushAsync();

    // Ticks should be 2010-01-01, 2019-06-01, 2020-01-01 (index 0, 1, 2).
    const slider = $('temporal-slider');
    assert.equal(slider.min, '0');
    assert.equal(slider.max, '2');
    assert.equal(slider.value, '2');
    assert.equal(slider.style.getPropertyValue('--control-value'), '2');
    assert.equal(slider.style.getPropertyValue('--attr-max'), '2');
    assert.match(slider.getAttribute('aria-valuetext'), /2020-01-01T00:00:00Z/);

    // At 2020-01-01 with includeUnknownSnapshots=false: v2 (statutory) + itv1 (interpretive), NO snap1.
    assert.ok($('temporal-statutory-list').querySelector('[data-version-id="v2"]'));
    assert.equal($('temporal-statutory-list').querySelector('[data-version-id="snap1"]'), null);
    assert.ok($('temporal-interpretive-list').querySelector('[data-version-id="itv1"]'));

    // Toggling includeUnknownSnapshots reveals snap1.
    $('temporal-include-unknown').checked = true;
    $('temporal-include-unknown').dispatchEvent(new window.Event('change'));
    assert.ok($('temporal-statutory-list').querySelector('[data-version-id="snap1"]'));

    // Moving slider to tick 0 (2010-01-01): v1 is statutory, itv1 is NOT yet valid.
    slider.value = '0';
    slider.dispatchEvent(new window.Event('input'));
    assert.equal(slider.style.getPropertyValue('--control-value'), '0');
    assert.match(slider.getAttribute('aria-valuetext'), /2010-01-01T00:00:00Z/);
    assert.ok($('temporal-statutory-list').querySelector('[data-version-id="v1"]'));
    assert.equal($('temporal-statutory-list').querySelector('[data-version-id="v2"]'), null);
    assert.equal($('temporal-interpretive-list').querySelector('[data-version-id="itv1"]'), null);

    // Clicking causal action marker selects terminates (v1) -> produces (v2) in Diff panel!
    const actMarker = $('temporal-timeline-svg').querySelector('[data-action-id="act:amend"]');
    assert.ok(actMarker);
    actMarker.dispatchEvent(new window.Event('click'));
    assert.equal($('temporal-diff-left').value, 'v1');
    assert.equal($('temporal-diff-right').value, 'v2');
    assert.ok($('temporal-diff-output').querySelector('del.temporal-diff-del'));
    assert.ok($('temporal-diff-output').querySelector('ins.temporal-diff-ins'));

    // Raw JSON inspector reflects getValidVersions and getItemHistory.
    const rawValid = JSON.parse($('temporal-raw-valid-json').textContent);
    const rawHistory = JSON.parse($('temporal-raw-history-json').textContent);
    assert.ok(rawValid.some(v => v.id === 'v2'));
    assert.equal(rawHistory.length, 1);
    assert.equal(rawHistory[0].id, 'act:amend');

    // Invalid JSON upload shows alert banner without replacing current valid dataset.
    window.SATTemporalViewer.handleUploadedJsonText('{not-valid-json');
    assert.equal($('temporal-validation-banner').hidden, false);
    assert.match($('temporal-validation-banner').textContent, /JSON_PARSE_ERROR/);
    assert.equal(window.SATTemporalViewer.getState().dataset.resourceId, 'pe:ley:28970');

    // Structurally invalid dataset fails validation cleanly.
    window.SATTemporalViewer.handleUploadedJsonText(JSON.stringify({items: [], versions: [{id: 'bad', itemId: 'missing'}]}));
    assert.equal($('temporal-validation-banner').hidden, false);
    assert.match($('temporal-validation-banner').textContent, /BROKEN_VERSION_ITEM/);

    // Valid uploaded JSON dataset loads cleanly.
    const uploaded = {
      title: 'Dataset cargado localmente',
      items: [{id: 'u:item', typeId: 'article', label: 'Art. Único'}],
      versions: [{id: 'u:v1', itemId: 'u:item', type: 'statutory', validityInterval: ['2022-05-01', null], text: 'Texto local.'}],
    };
    window.SATTemporalViewer.handleUploadedJsonText(JSON.stringify(uploaded));
    assert.equal($('temporal-validation-banner').hidden, true);
    assert.equal($('temporal-dataset-title').textContent, 'Dataset cargado localmente');
    assert.ok($('temporal-statutory-list').querySelector('[data-version-id="u:v1"]'));
  } finally {
    window.close();
  }
});
