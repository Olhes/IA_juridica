(function () {
  'use strict';

  var BASE = '/sat-graph/review';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var ROLE_PRIORITY = { subject: 4, object: 3, predicate: 2, clause: 1 };
  var ROLE_LABELS = {
    subject: 'Sujeto',
    predicate: 'Predicado',
    object: 'Objeto',
    clause: 'Cláusula',
  };
  var SUPERSCRIPTS = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
  };

  function bridge() {
    return typeof window !== 'undefined' ? window.SATReviewBridge : null;
  }

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  }

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      var keys = Object.keys(attrs);
      for (var i = 0; i < keys.length; i++) {
        node.setAttribute(keys[i], String(attrs[keys[i]]));
      }
    }
    return node;
  }

  function formatSuperscript(exp) {
    return String(exp).replace(/[0-9]/g, function (d) {
      return SUPERSCRIPTS[d] || d;
    });
  }

  function truncateLabel(text, maxLen) {
    var str = String(text || '');
    return str.length > maxLen ? str.slice(0, maxLen - 1) + '…' : str;
  }

  function formatBindingTerm(term) {
    if (!term) return '—';
    return term.label || term.value || '—';
  }

  function buildCodepointOffsets(text) {
    var b = bridge();
    if (b && typeof b.buildCpOffsets === 'function') {
      return b.buildCpOffsets(text);
    }
    var offsets = [];
    var utf16 = 0;
    for (var ch of String(text || '')) {
      offsets.push(utf16);
      utf16 += ch.length;
    }
    offsets.push(utf16);
    return Uint32Array.from(offsets);
  }

  function createController() {
    var root = document.getElementById('provenance-view');
    if (!root) return null;

    var state = {
      capabilities: null,
      graph: null,
      queryResult: null,
      occurrencesByToken: new Map(),
      sourceUnits: new Map(),
      selectedTokens: new Set(),
      selectedRowIndex: -1,
      selectedUnitId: '',
      compactMode: false,
      showNpcs: false,
      zoom: 1,
      baseViewBox: { width: 760, height: 320 },
      loadedDocSignature: '',
      busy: false,
      active: false,
    };

    var refs = {};

    function mountShell() {
      root.replaceChildren();
      var shell = el('div', undefined, 'ws-shell');

      // 1. Header bar
      var header = el('div', undefined, 'ws-header');
      var meta = el('div', undefined, 'ws-header-meta');
      meta.append(el('h2', 'GraphRAGProv · Grafo y proveniencia'));
      refs.modePill = el('span', 'Documento publicado', 'ws-badge ws-badge-published');
      refs.modePill.id = 'prov-mode-pill';
      refs.stats = el('span', 'Sin grafo cargado', 'muted');
      refs.stats.id = 'prov-stats';
      meta.append(refs.modePill, refs.stats);

      var actions = el('div', undefined, 'ws-header-actions');
      var extLabel = el('label', 'Extracción', 'ws-sr-only');
      extLabel.setAttribute('for', 'prov-extraction-mode');
      refs.extractionMode = el('select');
      refs.extractionMode.id = 'prov-extraction-mode';
      refs.extractionMode.setAttribute('aria-label', 'Modo de extracción de tripletas');
      var optDet = el('option', 'Extracción: Determinista');
      optDet.value = 'deterministic';
      refs.optCohereExt = el('option', 'Extracción: Cohere híbrido');
      refs.optCohereExt.value = 'hybrid_cohere';
      refs.optCohereExt.disabled = true;
      refs.extractionMode.append(optDet, refs.optCohereExt);

      refs.rebuildBtn = el('button', 'Reconstruir grafo');
      refs.rebuildBtn.type = 'button';
      refs.rebuildBtn.id = 'prov-rebuild-btn';

      refs.exportNtBtn = el('button', '↓ Exportar RDF-star (.nt)');
      refs.exportNtBtn.type = 'button';
      refs.exportNtBtn.id = 'prov-export-nt-btn';

      actions.append(extLabel, refs.extractionMode, refs.rebuildBtn, refs.exportNtBtn);
      header.append(meta, actions);
      shell.append(header);

      // 2. Query card
      var queryCard = el('div', undefined, 'ws-card prov-query-box');
      var queryHead = el('div', undefined, 'ws-card-head');
      queryHead.append(el('h3', 'Consulta SPARQL SELECT y compilador NL'));
      refs.queryMeta = el('span', 'Sin consulta ejecutada', 'muted');
      refs.queryMeta.id = 'prov-query-meta';
      queryHead.append(refs.queryMeta);
      queryCard.append(queryHead);

      refs.sampleChips = el('div', undefined, 'prov-chips');
      refs.sampleChips.id = 'prov-sample-chips';
      queryCard.append(refs.sampleChips);

      var nlRow = el('div', undefined, 'prov-nl-row');
      refs.nlInput = el('input');
      refs.nlInput.id = 'prov-nl-input';
      refs.nlInput.type = 'text';
      refs.nlInput.setAttribute('aria-label', 'Pregunta en lenguaje natural');
      refs.nlInput.placeholder = 'Pregunta en lenguaje natural (ej. ¿Qué obligaciones o plazos establece la norma?)';

      refs.nlMode = el('select');
      refs.nlMode.id = 'prov-nl-mode';
      refs.nlMode.setAttribute('aria-label', 'Compilador NL a SPARQL');
      var optNlDet = el('option', 'Compilador: Determinista');
      optNlDet.value = 'deterministic';
      refs.optCohereNl = el('option', 'Compilador: Cohere LLM');
      refs.optCohereNl.value = 'cohere';
      refs.optCohereNl.disabled = true;
      refs.nlMode.append(optNlDet, refs.optCohereNl);

      refs.nlRunBtn = el('button', 'Compilar y ejecutar');
      refs.nlRunBtn.type = 'button';
      refs.nlRunBtn.id = 'prov-nl-run-btn';
      nlRow.append(refs.nlInput, refs.nlMode, refs.nlRunBtn);
      queryCard.append(nlRow);

      var sparqlLabel = el('label', 'Consulta SPARQL SELECT editable');
      sparqlLabel.setAttribute('for', 'prov-sparql-input');
      refs.sparqlInput = el('textarea', undefined, 'prov-sparql-textarea');
      refs.sparqlInput.id = 'prov-sparql-input';
      refs.sparqlInput.spellcheck = false;
      refs.sparqlInput.placeholder = 'PREFIX legal: <http://iajuridica.pe/legal/>\nSELECT DISTINCT ?s ?o WHERE { ?s legal:obligates ?o . }';
      sparqlLabel.append(refs.sparqlInput);
      queryCard.append(sparqlLabel);

      var sparqlActions = el('div', undefined, 'ws-inline-controls');
      refs.sparqlRunBtn = el('button', 'Ejecutar SPARQL', 'primary');
      refs.sparqlRunBtn.type = 'button';
      refs.sparqlRunBtn.id = 'prov-sparql-run-btn';
      sparqlActions.append(refs.sparqlRunBtn);
      queryCard.append(sparqlActions);

      refs.warnings = el('div', undefined, 'ws-banner ws-banner-warn');
      refs.warnings.id = 'prov-warnings';
      refs.warnings.hidden = true;
      queryCard.append(refs.warnings);
      shell.append(queryCard);

      // 3. Split workbench grid: Answer Bindings + SVG Graph
      var grid = el('div', undefined, 'prov-grid');

      // Left: Answers & Polynomials
      var ansCard = el('div', undefined, 'ws-card');
      var ansHead = el('div', undefined, 'ws-card-head');
      ansHead.append(el('h3', 'Respuestas y polinomios de proveniencia N[X]'));
      var ansControls = el('div', undefined, 'ws-inline-controls');
      refs.compactToggle = el('button', 'Exacto N[X]');
      refs.compactToggle.type = 'button';
      refs.compactToggle.id = 'prov-compact-toggle';
      refs.compactToggle.setAttribute('aria-pressed', 'false');

      refs.npcsToggle = el('button', 'Ver NPCS prefijo');
      refs.npcsToggle.type = 'button';
      refs.npcsToggle.id = 'prov-npcs-toggle';
      refs.npcsToggle.setAttribute('aria-pressed', 'false');

      refs.clearSelBtn = el('button', 'Limpiar selección');
      refs.clearSelBtn.type = 'button';
      refs.clearSelBtn.id = 'prov-clear-selection-btn';

      ansControls.append(refs.compactToggle, refs.npcsToggle, refs.clearSelBtn);
      ansHead.append(ansControls);
      ansCard.append(ansHead);

      var tableWrap = el('div', undefined, 'prov-table-scroll');
      refs.resultsTable = el('table', undefined, 'prov-table');
      refs.resultsTable.id = 'prov-results-table';
      tableWrap.append(refs.resultsTable);
      ansCard.append(tableWrap);
      grid.append(ansCard);

      // Right: Interactive SVG Graph
      var graphCard = el('div', undefined, 'ws-card');
      var graphHead = el('div', undefined, 'ws-card-head');
      graphHead.append(el('h3', 'Grafo de proveniencia RDF-star'));
      var zoomControls = el('div', undefined, 'ws-inline-controls');
      refs.zoomOutBtn = el('button', '−');
      refs.zoomOutBtn.type = 'button';
      refs.zoomOutBtn.id = 'prov-zoom-out';
      refs.zoomOutBtn.setAttribute('aria-label', 'Alejar grafo');
      refs.zoomInBtn = el('button', '+');
      refs.zoomInBtn.type = 'button';
      refs.zoomInBtn.id = 'prov-zoom-in';
      refs.zoomInBtn.setAttribute('aria-label', 'Acercar grafo');
      refs.zoomResetBtn = el('button', 'Ajustar');
      refs.zoomResetBtn.type = 'button';
      refs.zoomResetBtn.id = 'prov-zoom-reset';
      zoomControls.append(refs.zoomOutBtn, refs.zoomInBtn, refs.zoomResetBtn);
      graphHead.append(zoomControls);
      graphCard.append(graphHead);

      var svgWrap = el('div', undefined, 'prov-svg-wrap');
      refs.graphSvg = svgEl('svg', {
        id: 'prov-graph-svg',
        class: 'prov-svg',
        viewBox: '0 0 760 320',
        role: 'img',
        'aria-label': 'Grafo de tripletas con proveniencia RDF-star',
      });
      svgWrap.append(refs.graphSvg);
      graphCard.append(svgWrap);

      refs.edgeSummary = el('div', 'Selecciona un término del polinomio, una arista del grafo o un fragmento resaltado.', 'prov-edge-summary');
      refs.edgeSummary.id = 'prov-edge-summary';
      graphCard.append(refs.edgeSummary);
      grid.append(graphCard);
      shell.append(grid);

      // 4. Source Evidence Passage Viewer
      var passageCard = el('div', undefined, 'ws-card');
      var passageHead = el('div', undefined, 'ws-card-head');
      passageHead.append(el('h3', 'Evidencia en texto fuente'));
      var legend = el('div', undefined, 'prov-legend');
      var roles = ['subject', 'predicate', 'object', 'clause'];
      for (var ri = 0; ri < roles.length; ri++) {
        var rKey = roles[ri];
        var item = el('span');
        var sampleMark = el('mark', ROLE_LABELS[rKey], 'prov-mark');
        sampleMark.dataset.role = rKey;
        item.append(sampleMark);
        legend.append(item);
      }
      passageHead.append(legend);
      passageCard.append(passageHead);

      var unitControls = el('div', undefined, 'prov-unit-controls');
      var unitLabel = el('label', 'Unidad de texto', 'ws-sr-only');
      unitLabel.setAttribute('for', 'prov-unit-select');
      refs.unitSelect = el('select');
      refs.unitSelect.id = 'prov-unit-select';
      refs.unitSelect.setAttribute('aria-label', 'Unidad documental de evidencia');
      refs.jumpStructureBtn = el('button', 'Abrir en Estructura ↗');
      refs.jumpStructureBtn.type = 'button';
      refs.jumpStructureBtn.id = 'prov-jump-structure-btn';
      refs.jumpStructureBtn.disabled = true;
      unitControls.append(unitLabel, refs.unitSelect, refs.jumpStructureBtn);
      passageCard.append(unitControls);

      refs.passage = el('div', 'Selecciona un documento para visualizar los fragmentos anclados.', 'prov-passage');
      refs.passage.id = 'prov-passage';
      passageCard.append(refs.passage);
      shell.append(passageCard);

      // 5. Collapsible NPCS Polynomial Verifier
      var verifier = el('details', undefined, 'prov-verifier-details');
      verifier.append(el('summary', 'Verificador de polinomios NPCS (N[X])'));
      var vBody = el('div', undefined, 'prov-verifier-body');
      var vLabel = el('label', 'Expresión en prefijo NPCS o SparqlProv');
      vLabel.setAttribute('for', 'prov-npcs-verifier-input');
      refs.verifierInput = el('textarea');
      refs.verifierInput.id = 'prov-npcs-verifier-input';
      refs.verifierInput.spellcheck = false;
      refs.verifierInput.placeholder = '(+ (* occ_000000000001 occ_000000000002) occ_000000000003)';
      vLabel.append(refs.verifierInput);
      var vActions = el('div', undefined, 'ws-inline-controls');
      refs.verifierBtn = el('button', 'Verificar polinomio');
      refs.verifierBtn.type = 'button';
      refs.verifierBtn.id = 'prov-npcs-verifier-btn';
      vActions.append(refs.verifierBtn);
      refs.verifierOutput = el('pre', 'Introduce una expresión NPCS para expandirla en N[X].');
      refs.verifierOutput.id = 'prov-npcs-verifier-output';
      vBody.append(vLabel, vActions, refs.verifierOutput);
      verifier.append(vBody);
      shell.append(verifier);

      root.append(shell);
      bindEvents();
    }

    function currentContext() {
      var b = bridge();
      return b ? b.getContext() : { doc: null, draft: null, dirty: false };
    }

    function draftPayloadIfDirty() {
      var ctx = currentContext();
      if (ctx.dirty && ctx.doc && ctx.doc.editable && ctx.draft) {
        return ctx.draft;
      }
      return null;
    }

    function updateModePill() {
      var ctx = currentContext();
      if (!ctx.doc) {
        refs.modePill.textContent = 'Sin documento';
        refs.modePill.className = 'ws-badge';
        return;
      }
      if (ctx.dirty && ctx.doc.editable) {
        refs.modePill.textContent = 'Borrador sin publicar';
        refs.modePill.className = 'ws-badge ws-badge-draft';
      } else if (ctx.doc.candidate && !ctx.doc.published) {
        refs.modePill.textContent = 'Candidato sin publicar';
        refs.modePill.className = 'ws-badge ws-badge-draft';
      } else {
        refs.modePill.textContent = 'Documento publicado';
        refs.modePill.className = 'ws-badge ws-badge-published';
      }
    }

    function syncCapabilitiesUI() {
      var caps = state.capabilities;
      var cohereOk = Boolean(caps && caps.cohere_available);
      refs.optCohereExt.disabled = !cohereOk;
      refs.optCohereNl.disabled = !cohereOk;
      var reason = cohereOk
        ? 'Disponible con Cohere (' + (caps.cohere_model || 'modelo configurado') + ')'
        : 'COHERE_API_KEY no configurada en el servidor; modo determinista disponible sin conexión.';
      refs.optCohereExt.title = reason;
      refs.optCohereNl.title = reason;
      refs.optCohereExt.textContent = cohereOk
        ? 'Extracción: Cohere híbrido'
        : 'Extracción: Cohere híbrido (sin API key)';
      refs.optCohereNl.textContent = cohereOk
        ? 'Compilador: Cohere LLM'
        : 'Compilador: Cohere LLM (sin API key)';
      if (!cohereOk) {
        if (refs.extractionMode.value === 'hybrid_cohere') refs.extractionMode.value = 'deterministic';
        if (refs.nlMode.value === 'cohere') refs.nlMode.value = 'deterministic';
      }
    }

    async function ensureCapabilities() {
      if (state.capabilities) return state.capabilities;
      var b = bridge();
      if (!b) return null;
      try {
        state.capabilities = await b.request(BASE + '/provenance/capabilities');
        syncCapabilitiesUI();
        renderSampleChips();
      } catch (err) {
        b.notify('No se pudieron cargar las capacidades de proveniencia: ' + err.message, true);
      }
      return state.capabilities;
    }

    function indexGraphData(graphData, queryData) {
      state.occurrencesByToken = new Map();
      state.sourceUnits = new Map();
      var gUnits = (graphData && graphData.source_units) || {};
      var unitKeys = Object.keys(gUnits);
      for (var i = 0; i < unitKeys.length; i++) {
        state.sourceUnits.set(unitKeys[i], gUnits[unitKeys[i]]);
      }
      var qUnits = (queryData && queryData.source_units) || {};
      var qUnitKeys = Object.keys(qUnits);
      for (var qi = 0; qi < qUnitKeys.length; qi++) {
        state.sourceUnits.set(qUnitKeys[qi], qUnits[qUnitKeys[qi]]);
      }

      var gOccs = (graphData && graphData.occurrences) || [];
      for (var oi = 0; oi < gOccs.length; oi++) {
        state.occurrencesByToken.set(gOccs[oi].token, gOccs[oi]);
      }
      var qOccs = (queryData && queryData.occurrences) || {};
      var qOccKeys = Object.keys(qOccs);
      for (var qoi = 0; qoi < qOccKeys.length; qoi++) {
        state.occurrencesByToken.set(qOccKeys[qoi], qOccs[qOccKeys[qoi]]);
      }
    }

    function renderSampleChips() {
      refs.sampleChips.replaceChildren();
      var items = (state.graph && Array.isArray(state.graph.sample_queries) && state.graph.sample_queries.length)
        ? state.graph.sample_queries
        : ((state.capabilities && state.capabilities.templates) || []);
      if (!items.length) return;
      for (var i = 0; i < items.length; i++) {
        (function (item) {
          var btn = el('button', item.title || item.id, 'prov-chip');
          btn.type = 'button';
          btn.dataset.sampleId = item.id || String(i);
          if (item.description || item.highlights_algebra) {
            btn.title = item.description || item.highlights_algebra;
          }
          btn.addEventListener('click', function () {
            if (item.question) refs.nlInput.value = item.question;
            refs.sparqlInput.value = item.sparql || '';
            void runQuery({ sparql: item.sparql || '', question: item.question || null });
          });
          refs.sampleChips.append(btn);
        })(items[i]);
      }
    }

    function renderUnitSelector() {
      var units = Array.from(state.sourceUnits.values());
      refs.unitSelect.replaceChildren();
      if (!units.length) {
        var opt = el('option', 'Sin unidades de texto');
        opt.value = '';
        refs.unitSelect.append(opt);
        state.selectedUnitId = '';
        refs.jumpStructureBtn.disabled = true;
        return;
      }
      for (var i = 0; i < units.length; i++) {
        var u = units[i];
        var option = el('option', u.label || u.id);
        option.value = u.id;
        refs.unitSelect.append(option);
      }
      if (!state.selectedUnitId || !state.sourceUnits.has(state.selectedUnitId)) {
        state.selectedUnitId = units[0].id;
      }
      refs.unitSelect.value = state.selectedUnitId;
      updateJumpButtonState();
    }

    function updateJumpButtonState() {
      var ctx = currentContext();
      var components = (ctx.draft && ctx.draft.components) || [];
      var canJump = Boolean(
        state.selectedUnitId &&
        components.some(function (c) { return c.id === state.selectedUnitId; })
      );
      refs.jumpStructureBtn.disabled = !canJump;
    }

    function renderResultsTable() {
      refs.resultsTable.replaceChildren();
      var qr = state.queryResult;
      if (!qr) {
        var emptyBody = el('tbody');
        var emptyTr = el('tr');
        emptyTr.append(el('td', 'Ejecuta una consulta SPARQL o selecciona una plantilla para ver los polinomios N[X].', 'muted'));
        emptyBody.append(emptyTr);
        refs.resultsTable.append(emptyBody);
        return;
      }

      var vars = Array.isArray(qr.variables) ? qr.variables : [];
      var thead = el('thead');
      var headRow = el('tr');
      for (var vi = 0; vi < vars.length; vi++) {
        headRow.append(el('th', '?' + vars[vi]));
      }
      headRow.append(el('th', 'Testigos'), el('th', 'Polinomio de proveniencia N[X]'));
      thead.append(headRow);
      refs.resultsTable.append(thead);

      var tbody = el('tbody');
      var rows = Array.isArray(qr.rows) ? qr.rows : [];
      if (!rows.length) {
        var trNone = el('tr');
        var tdNone = el('td', 'La consulta no produjo resultados para este documento.', 'muted');
        tdNone.colSpan = vars.length + 2;
        trNone.append(tdNone);
        tbody.append(trNone);
        refs.resultsTable.append(tbody);
        return;
      }

      for (var ri = 0; ri < rows.length; ri++) {
        (function (row, idx) {
          var tr = el('tr');
          tr.dataset.rowIndex = String(idx);
          if (state.selectedRowIndex === idx) tr.classList.add('prov-row-active');

          for (var ci = 0; ci < vars.length; ci++) {
            var vName = vars[ci];
            var term = row.bindings ? row.bindings[vName] : null;
            var td = el('td', formatBindingTerm(term));
            if (term && term.value) td.title = term.value;
            tr.append(td);
          }

          var countTd = el('td', String(row.witness_count != null ? row.witness_count : 0));
          tr.append(countTd);

          var polyTd = el('td');
          var polyCell = el('div', undefined, 'prov-poly-cell');
          var exprWrap = el('div', undefined, 'prov-poly-expr');
          var monomials = Array.isArray(row.monomials) ? row.monomials : [];

          if (!monomials.length) {
            exprWrap.append(el('span', state.compactMode ? (row.compact_polynomial || '1') : (row.polynomial || '1'), 'muted'));
          } else {
            var seenCompact = new Set();
            var renderedMonomials = 0;
            for (var mi = 0; mi < monomials.length; mi++) {
              var mon = monomials[mi];
              var factors = Array.isArray(mon.factors) ? mon.factors : [];
              var factorTokens = factors.map(function (f) { return f.token; });
              if (state.compactMode) {
                var cKey = factorTokens.join(',');
                if (seenCompact.has(cKey)) continue;
                seenCompact.add(cKey);
              }
              if (renderedMonomials > 0) {
                exprWrap.append(el('span', '⊕', 'prov-op'));
              }
              renderedMonomials++;

              var monSpan = el('span', undefined, 'prov-monomial');
              monSpan.dataset.monomialTokens = factorTokens.join(',');
              var allActive = factorTokens.length > 0 && factorTokens.every(function (t) { return state.selectedTokens.has(t); });
              if (allActive) monSpan.classList.add('prov-active');

              if (!state.compactMode && mon.coeff > 1) {
                exprWrap.append(el('span', String(mon.coeff) + '·', 'prov-op'));
              }

              if (factorTokens.length > 1) {
                var groupBtn = el('button', '⊗×' + factorTokens.length, 'prov-monomial-btn');
                groupBtn.type = 'button';
                groupBtn.dataset.monomialTokens = factorTokens.join(',');
                groupBtn.title = 'Resaltar conjunción completa: ' + factorTokens.join(' ⊗ ');
                if (allActive) groupBtn.classList.add('prov-active');
                (function (tokensCopy, rowIdx) {
                  groupBtn.addEventListener('click', function () {
                    state.selectedRowIndex = rowIdx;
                    selectTokens(tokensCopy, { scrollPassage: true });
                  });
                })(factorTokens.slice(), idx);
                monSpan.append(groupBtn);
              }

              for (var fi = 0; fi < factors.length; fi++) {
                if (fi > 0) {
                  monSpan.append(el('span', '⊗', 'prov-op'));
                }
                (function (factor, rowIdx) {
                  var label = factor.token + (!state.compactMode && factor.exp > 1 ? formatSuperscript(factor.exp) : '');
                  var chip = el('button', label, 'prov-token-chip');
                  chip.type = 'button';
                  chip.dataset.token = factor.token;
                  chip.title = 'Resaltar ocurrencia ' + factor.token;
                  if (state.selectedTokens.has(factor.token)) chip.classList.add('prov-active');
                  chip.addEventListener('click', function () {
                    state.selectedRowIndex = rowIdx;
                    selectTokens([factor.token], { scrollPassage: true });
                  });
                  monSpan.append(chip);
                })(factors[fi], idx);
              }
              exprWrap.append(monSpan);
            }
          }
          polyCell.append(exprWrap);

          if (state.showNpcs && row.npcs_prefix) {
            polyCell.append(el('code', row.npcs_prefix, 'prov-npcs-code'));
          }
          polyTd.append(polyCell);
          tr.append(polyTd);
          tbody.append(tr);
        })(rows[ri], ri);
      }
      refs.resultsTable.append(tbody);
    }

    function activeSubgraph() {
      if (state.queryResult && state.queryResult.subgraph && state.queryResult.subgraph.edges.length) {
        return state.queryResult.subgraph;
      }
      if (state.graph && state.graph.subgraph) {
        return state.graph.subgraph;
      }
      return { nodes: [], edges: [] };
    }

    function computeGraphLayout(subgraph) {
      var nodes = subgraph.nodes || [];
      var edges = subgraph.edges || [];
      var outDeg = new Map();
      var inDeg = new Map();
      for (var i = 0; i < nodes.length; i++) {
        outDeg.set(nodes[i].id, 0);
        inDeg.set(nodes[i].id, 0);
      }
      for (var ei = 0; ei < edges.length; ei++) {
        outDeg.set(edges[ei].source, (outDeg.get(edges[ei].source) || 0) + 1);
        inDeg.set(edges[ei].target, (inDeg.get(edges[ei].target) || 0) + 1);
      }

      var cols = [[], [], []];
      for (var ni = 0; ni < nodes.length; ni++) {
        var n = nodes[ni];
        var od = outDeg.get(n.id) || 0;
        var idg = inDeg.get(n.id) || 0;
        if (od > 0 && idg === 0) cols[0].push(n);
        else if (od > 0 && idg > 0) cols[1].push(n);
        else cols[2].push(n);
      }
      if (!cols[0].length && !cols[1].length && cols[2].length) {
        cols[0] = cols[2].splice(0, Math.ceil(cols[2].length / 2));
      }

      var activeCols = cols.filter(function (c) { return c.length > 0; });
      for (var ci = 0; ci < activeCols.length; ci++) {
        activeCols[ci].sort(function (a, b) {
          var degDiff = ((outDeg.get(b.id) || 0) + (inDeg.get(b.id) || 0)) -
            ((outDeg.get(a.id) || 0) + (inDeg.get(a.id) || 0));
          return degDiff || String(a.id).localeCompare(String(b.id));
        });
      }

      var nodeW = 168;
      var nodeH = 34;
      var colGap = activeCols.length > 1 ? 250 : 220;
      var rowGap = 62;
      var padX = 28;
      var padY = 30;
      var maxRows = 1;
      for (var k = 0; k < activeCols.length; k++) {
        if (activeCols[k].length > maxRows) maxRows = activeCols[k].length;
      }

      var positions = new Map();
      var totalH = Math.max(290, padY * 2 + maxRows * rowGap);
      var totalW = Math.max(760, padX * 2 + Math.max(1, activeCols.length - 1) * colGap + nodeW);

      for (var cIdx = 0; cIdx < activeCols.length; cIdx++) {
        var colNodes = activeCols[cIdx];
        var colHeight = colNodes.length * rowGap;
        var startY = Math.max(padY, (totalH - colHeight) / 2);
        var x = padX + cIdx * colGap;
        for (var rIdx = 0; rIdx < colNodes.length; rIdx++) {
          var y = startY + rIdx * rowGap;
          positions.set(colNodes[rIdx].id, {
            x: x,
            y: y,
            cx: x + nodeW / 2,
            cy: y + nodeH / 2,
            w: nodeW,
            h: nodeH,
          });
        }
      }

      return { positions: positions, width: totalW, height: totalH };
    }

    function applySvgZoom() {
      var w = Math.round(state.baseViewBox.width / state.zoom);
      var h = Math.round(state.baseViewBox.height / state.zoom);
      var x = Math.round((state.baseViewBox.width - w) / 2);
      var y = Math.round((state.baseViewBox.height - h) / 2);
      refs.graphSvg.setAttribute('viewBox', x + ' ' + y + ' ' + w + ' ' + h);
    }

    function renderSvgGraph() {
      refs.graphSvg.replaceChildren();
      var subgraph = activeSubgraph();
      if (!subgraph.nodes.length) {
        state.baseViewBox = { width: 760, height: 220 };
        applySvgZoom();
        var msg = svgEl('text', { x: 380, y: 110, 'text-anchor': 'middle', class: 'temporal-axis-label' });
        msg.textContent = 'Sin tripletas ancladas para mostrar en el grafo.';
        refs.graphSvg.append(msg);
        return;
      }

      var layout = computeGraphLayout(subgraph);
      state.baseViewBox = { width: layout.width, height: layout.height };
      applySvgZoom();

      var defs = svgEl('defs');
      var marker = svgEl('marker', {
        id: 'prov-arrow',
        viewBox: '0 0 10 10',
        refX: '9',
        refY: '5',
        markerWidth: '7',
        markerHeight: '7',
        orient: 'auto-start-reverse',
      });
      marker.append(svgEl('path', { d: 'M 0 1 L 10 5 L 0 9 z', fill: 'currentColor' }));
      defs.append(marker);
      refs.graphSvg.append(defs);

      var edgesGroup = svgEl('g');
      var incidentByNode = new Map();
      var edges = subgraph.edges || [];

      for (var ei = 0; ei < edges.length; ei++) {
        (function (edge) {
          var src = layout.positions.get(edge.source);
          var dst = layout.positions.get(edge.target);
          if (!src || !dst) return;

          if (!incidentByNode.has(edge.source)) incidentByNode.set(edge.source, []);
          if (!incidentByNode.has(edge.target)) incidentByNode.set(edge.target, []);
          incidentByNode.get(edge.source).push(edge.token);
          incidentByNode.get(edge.target).push(edge.token);

          var pIdx = typeof edge.parallel_index === 'number' ? edge.parallel_index : 0;
          var pCount = typeof edge.parallel_count === 'number' && edge.parallel_count > 0 ? edge.parallel_count : 1;
          var offsetFactor = pIdx - (pCount - 1) / 2;

          var sx = src.cx;
          var sy = src.cy;
          var tx = dst.cx;
          var ty = dst.cy;
          var d;
          var labelX;
          var labelY;

          if (edge.source === edge.target) {
            var loopR = 28 + Math.abs(offsetFactor) * 18;
            d = 'M ' + (src.x + src.w * 0.7) + ' ' + src.y +
              ' Q ' + (src.x + src.w + loopR) + ' ' + (src.y - loopR) +
              ' ' + (src.x + src.w * 0.3) + ' ' + src.y;
            labelX = src.cx + loopR * 0.5;
            labelY = src.y - loopR * 0.55;
          } else {
            if (src.x + src.w < dst.x) {
              sx = src.x + src.w;
              tx = dst.x;
            } else if (dst.x + dst.w < src.x) {
              sx = src.x;
              tx = dst.x + dst.w;
            }
            var mx = (sx + tx) / 2;
            var my = (sy + ty) / 2;
            var dx = tx - sx;
            var dy = ty - sy;
            var dist = Math.hypot(dx, dy) || 1;
            var nx = -dy / dist;
            var ny = dx / dist;
            var curve = offsetFactor * 36;
            var cx = mx + nx * curve;
            var cy = my + ny * curve;
            d = 'M ' + sx.toFixed(1) + ' ' + sy.toFixed(1) +
              ' Q ' + cx.toFixed(1) + ' ' + cy.toFixed(1) +
              ' ' + tx.toFixed(1) + ' ' + ty.toFixed(1);
            labelX = 0.25 * sx + 0.5 * cx + 0.25 * tx;
            labelY = 0.25 * sy + 0.5 * cy + 0.25 * ty - 5;
          }

          var g = svgEl('g', {
            class: 'prov-svg-edge' + (state.selectedTokens.has(edge.token) ? ' prov-active' : ''),
            'data-token': edge.token,
            role: 'button',
            tabindex: '0',
            'aria-label': (edge.predicate || 'relación') + ' (' + edge.token + ')',
          });
          var title = svgEl('title');
          title.textContent = edge.predicate + ' [' + edge.token + ']';
          g.append(title);
          g.append(svgEl('path', { d: d, 'marker-end': 'url(#prov-arrow)' }));
          var label = svgEl('text', {
            x: labelX.toFixed(1),
            y: labelY.toFixed(1),
            'text-anchor': 'middle',
          });
          label.textContent = truncateLabel(edge.predicate, 22);
          g.append(label);

          var activate = function () {
            selectTokens([edge.token], { scrollPassage: true });
          };
          g.addEventListener('click', activate);
          g.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              activate();
            }
          });
          edgesGroup.append(g);
        })(edges[ei]);
      }
      refs.graphSvg.append(edgesGroup);

      var nodesGroup = svgEl('g');
      var nodes = subgraph.nodes || [];
      for (var ni = 0; ni < nodes.length; ni++) {
        (function (node) {
          var pos = layout.positions.get(node.id);
          if (!pos) return;
          var incident = incidentByNode.get(node.id) || [];
          var isNodeActive = incident.some(function (t) { return state.selectedTokens.has(t); });
          var g = svgEl('g', {
            class: 'prov-svg-node' + (isNodeActive ? ' prov-active' : ''),
            'data-node-id': node.id,
            role: 'button',
            tabindex: '0',
            'aria-label': node.label || node.id,
          });
          var title = svgEl('title');
          title.textContent = (node.label || node.id) + (node.value ? ' (' + node.value + ')' : '');
          g.append(title);
          g.append(svgEl('rect', { x: pos.x, y: pos.y, width: pos.w, height: pos.h }));
          var txt = svgEl('text', {
            x: pos.cx,
            y: pos.cy + 4,
            'text-anchor': 'middle',
          });
          txt.textContent = truncateLabel(node.label || node.id, 24);
          g.append(txt);

          var activateNode = function () {
            if (incident.length) selectTokens(incident, { scrollPassage: true });
          };
          g.addEventListener('click', activateNode);
          g.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              activateNode();
            }
          });
          nodesGroup.append(g);
        })(nodes[ni]);
      }
      refs.graphSvg.append(nodesGroup);
    }

    function clampRange(start, end, cpLen) {
      var s = Math.max(0, Math.min(cpLen, Number(start)));
      var e = Math.max(0, Math.min(cpLen, Number(end)));
      if (!Number.isFinite(s) || !Number.isFinite(e) || e <= s) return null;
      return { start: s, end: e };
    }

    function collectUnitSpanEntries(unit, unitOccs, cpLen) {
      var entries = [];
      for (var i = 0; i < unitOccs.length; i++) {
        var occ = unitOccs[i];
        var spans = occ.spans || {};
        var baseOffset = typeof spans.component_start_in_doc === 'number'
          ? spans.component_start_in_doc
          : (typeof unit.global_start === 'number' ? unit.global_start : 0);

        if (spans.evidence_span) {
          var evRange = clampRange(spans.evidence_span.start, spans.evidence_span.end, cpLen);
          if (evRange) {
            entries.push({ start: evRange.start, end: evRange.end, role: 'clause', token: occ.token });
          }
        } else if (spans.doc_evidence_span) {
          var docEv = clampRange(spans.doc_evidence_span.start - baseOffset, spans.doc_evidence_span.end - baseOffset, cpLen);
          if (docEv) {
            entries.push({ start: docEv.start, end: docEv.end, role: 'clause', token: occ.token });
          }
        }

        var roleMap = [
          ['subject', spans.subject_span],
          ['predicate', spans.predicate_span],
          ['object', spans.object_span],
        ];
        for (var r = 0; r < roleMap.length; r++) {
          var roleName = roleMap[r][0];
          var roleSpan = roleMap[r][1];
          if (!roleSpan) continue;
          var localRange = clampRange(roleSpan.start - baseOffset, roleSpan.end - baseOffset, cpLen);
          if (localRange) {
            entries.push({ start: localRange.start, end: localRange.end, role: roleName, token: occ.token });
          }
        }
      }
      return entries;
    }

    function renderPassage(scrollToActive) {
      refs.passage.replaceChildren();
      var unit = state.sourceUnits.get(state.selectedUnitId);
      if (!unit) {
        refs.passage.textContent = 'No hay unidad de texto seleccionada.';
        return;
      }

      var text = String(unit.text || '');
      var offsets = buildCodepointOffsets(text);
      var cpLen = Math.max(0, offsets.length - 1);

      var unitOccs = [];
      state.occurrencesByToken.forEach(function (occ) {
        if (occ && occ.spans && occ.spans.component_id === unit.id) {
          unitOccs.push(occ);
        }
      });

      var spanEntries = collectUnitSpanEntries(unit, unitOccs, cpLen);
      if (!spanEntries.length) {
        refs.passage.textContent = text;
        return;
      }

      var cutsSet = new Set([0, cpLen]);
      for (var i = 0; i < spanEntries.length; i++) {
        cutsSet.add(spanEntries[i].start);
        cutsSet.add(spanEntries[i].end);
      }
      var cuts = Array.from(cutsSet).sort(function (a, b) { return a - b; });
      var frag = document.createDocumentFragment();
      var firstActiveMark = null;

      for (var ci = 0; ci < cuts.length - 1; ci++) {
        var segStart = cuts[ci];
        var segEnd = cuts[ci + 1];
        if (segEnd <= segStart) continue;
        var slice = text.slice(offsets[segStart], offsets[segEnd]);
        if (!slice) continue;

        var covering = [];
        for (var si = 0; si < spanEntries.length; si++) {
          var item = spanEntries[si];
          if (item.start <= segStart && item.end >= segEnd) {
            covering.push(item);
          }
        }

        if (!covering.length) {
          frag.append(document.createTextNode(slice));
          continue;
        }

        var specificCover = covering.filter(function (cov) { return cov.role !== 'clause'; });
        var effectiveCover = specificCover.length ? specificCover : covering;
        var tokenSet = new Set();
        var bestRole = 'clause';
        var bestScore = -1;
        var hasActive = false;
        for (var k = 0; k < effectiveCover.length; k++) {
          var cov = effectiveCover[k];
          tokenSet.add(cov.token);
          var isTokActive = state.selectedTokens.has(cov.token);
          if (isTokActive) hasActive = true;
          var score = (isTokActive ? 10 : 0) + (ROLE_PRIORITY[cov.role] || 0);
          if (score > bestScore) {
            bestScore = score;
            bestRole = cov.role;
          }
        }

        var tokensArr = Array.from(tokenSet);
        var mark = el('mark', slice, 'prov-mark' + (hasActive ? ' prov-mark-active' : ''));
        mark.dataset.role = bestRole;
        mark.dataset.tokens = tokensArr.join(',');
        mark.setAttribute('tabindex', '0');
        mark.title = (ROLE_LABELS[bestRole] || bestRole) + ' · ' + tokensArr.join(', ');

        (function (tokensForMark) {
          var onActivate = function () {
            selectTokens(tokensForMark, { scrollPassage: false });
          };
          mark.addEventListener('click', onActivate);
          mark.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              onActivate();
            }
          });
        })(tokensArr);

        if (hasActive && !firstActiveMark) {
          firstActiveMark = mark;
        }
        frag.append(mark);
      }

      refs.passage.append(frag);
      if (scrollToActive && firstActiveMark && typeof firstActiveMark.scrollIntoView === 'function') {
        firstActiveMark.scrollIntoView({ block: 'nearest' });
      }
    }

    function updateEdgeSummary() {
      var tokens = Array.from(state.selectedTokens);
      if (!tokens.length) {
        refs.edgeSummary.textContent = 'Selecciona un término del polinomio, una arista del grafo o un fragmento resaltado.';
        return;
      }
      var lines = [];
      for (var i = 0; i < Math.min(tokens.length, 3); i++) {
        var occ = state.occurrencesByToken.get(tokens[i]);
        if (occ) {
          lines.push(
            occ.token + ': ' +
            formatBindingTerm(occ.subject) + ' — ' +
            formatBindingTerm(occ.predicate) + ' → ' +
            formatBindingTerm(occ.object) +
            ' [' + (occ.origin || 'deterministic') + ']'
          );
        } else {
          lines.push(tokens[i]);
        }
      }
      if (tokens.length > 3) {
        lines.push('… y ' + (tokens.length - 3) + ' ocurrencia(s) más.');
      }
      refs.edgeSummary.textContent = lines.join(' | ');
    }

    function syncHighlightsAcrossPanels(scrollPassage) {
      // Polynomial chips & monomial groups
      var tokenChips = refs.resultsTable.querySelectorAll('[data-token]');
      for (var i = 0; i < tokenChips.length; i++) {
        tokenChips[i].classList.toggle('prov-active', state.selectedTokens.has(tokenChips[i].dataset.token));
      }
      var monomialEls = refs.resultsTable.querySelectorAll('[data-monomial-tokens]');
      for (var m = 0; m < monomialEls.length; m++) {
        var mTokens = (monomialEls[m].dataset.monomialTokens || '').split(',').filter(Boolean);
        var mActive = mTokens.length > 0 && mTokens.every(function (t) { return state.selectedTokens.has(t); });
        monomialEls[m].classList.toggle('prov-active', mActive);
      }
      var rows = refs.resultsTable.querySelectorAll('tbody tr[data-row-index]');
      for (var r = 0; r < rows.length; r++) {
        rows[r].classList.toggle('prov-row-active', Number(rows[r].dataset.rowIndex) === state.selectedRowIndex);
      }

      // SVG edges & nodes
      var svgEdges = refs.graphSvg.querySelectorAll('.prov-svg-edge[data-token]');
      var activeEdgeTokens = new Set();
      for (var e = 0; e < svgEdges.length; e++) {
        var tok = svgEdges[e].getAttribute('data-token');
        var active = state.selectedTokens.has(tok);
        svgEdges[e].classList.toggle('prov-active', active);
        if (active) activeEdgeTokens.add(tok);
      }

      var subgraph = activeSubgraph();
      var activeNodes = new Set();
      for (var se = 0; se < (subgraph.edges || []).length; se++) {
        var edge = subgraph.edges[se];
        if (activeEdgeTokens.has(edge.token)) {
          activeNodes.add(edge.source);
          activeNodes.add(edge.target);
        }
      }
      var svgNodes = refs.graphSvg.querySelectorAll('.prov-svg-node[data-node-id]');
      for (var n = 0; n < svgNodes.length; n++) {
        var nid = svgNodes[n].getAttribute('data-node-id');
        svgNodes[n].classList.toggle('prov-active', activeNodes.has(nid));
      }

      // Auto-switch passage component if selected occurrence lives in another unit
      var switchedUnit = false;
      var selectedList = Array.from(state.selectedTokens);
      if (selectedList.length) {
        var firstOcc = state.occurrencesByToken.get(selectedList[0]);
        var targetUnitId = firstOcc && firstOcc.spans ? firstOcc.spans.component_id : '';
        if (targetUnitId && state.sourceUnits.has(targetUnitId) && targetUnitId !== state.selectedUnitId) {
          state.selectedUnitId = targetUnitId;
          refs.unitSelect.value = targetUnitId;
          updateJumpButtonState();
          switchedUnit = true;
        }
      }

      renderPassage(Boolean(scrollPassage || switchedUnit));
      updateEdgeSummary();
    }

    function selectTokens(tokens, options) {
      state.selectedTokens = new Set((tokens || []).filter(Boolean));
      syncHighlightsAcrossPanels(Boolean(options && options.scrollPassage));
    }

    function showWarnings(warnings) {
      var list = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
      if (!list.length) {
        refs.warnings.hidden = true;
        refs.warnings.textContent = '';
        return;
      }
      refs.warnings.hidden = false;
      refs.warnings.textContent = list.join(' · ');
    }

    async function loadGraph(force) {
      var ctx = currentContext();
      var b = bridge();
      if (!ctx.doc || !b) return;
      var signature = ctx.doc.id + '|' + (ctx.dirty ? 'draft' : 'pub') + '|' + refs.extractionMode.value;
      if (!force && state.loadedDocSignature === signature && state.graph) return;

      state.busy = true;
      refs.rebuildBtn.disabled = true;
      updateModePill();
      try {
        await ensureCapabilities();
        var body = {
          mode: refs.extractionMode.value || 'deterministic',
          draft_edition: draftPayloadIfDirty(),
        };
        var graph = await b.post(BASE + '/documents/' + encodeURIComponent(ctx.doc.id) + '/provenance-graph', body);
        state.graph = graph;
        state.queryResult = null;
        state.selectedTokens.clear();
        state.selectedRowIndex = -1;
        state.loadedDocSignature = signature;
        indexGraphData(graph, null);

        var stats = graph.stats || {};
        refs.stats.textContent =
          (stats.occurrences != null ? stats.occurrences : (graph.occurrences || []).length) + ' ocurrencias · ' +
          (stats.units != null ? stats.units : state.sourceUnits.size) + ' unidades · ' +
          (stats.predicates != null ? stats.predicates : (graph.predicates || []).length) + ' predicados';

        renderSampleChips();
        renderUnitSelector();
        renderResultsTable();
        renderSvgGraph();
        renderPassage(false);
        updateEdgeSummary();
        showWarnings(graph.unlocalized_discarded ? ['Se descartaron ' + graph.unlocalized_discarded + ' tripletas sin anclaje verificable en el texto.'] : []);

        var defaultSample = (graph.sample_queries && graph.sample_queries[0]) ||
          (state.capabilities && state.capabilities.templates && state.capabilities.templates[0]);
        if (defaultSample && defaultSample.sparql) {
          refs.sparqlInput.value = defaultSample.sparql;
          await runQuery({ sparql: defaultSample.sparql, question: defaultSample.question || null });
        }
      } catch (err) {
        b.notify('Error al construir el grafo de proveniencia: ' + err.message, true);
      } finally {
        state.busy = false;
        refs.rebuildBtn.disabled = false;
      }
    }

    async function runQuery(override) {
      var ctx = currentContext();
      var b = bridge();
      if (!ctx.doc || !b) return;
      var sparql = override && override.sparql !== undefined ? override.sparql : refs.sparqlInput.value;
      var question = override && override.question !== undefined ? override.question : refs.nlInput.value;
      if (!String(sparql || '').trim() && !String(question || '').trim()) {
        b.notify('Escribe una pregunta en lenguaje natural o una consulta SPARQL SELECT.', true);
        return;
      }

      refs.sparqlRunBtn.disabled = true;
      refs.nlRunBtn.disabled = true;
      try {
        var payload = {
          question: String(question || '').trim() || null,
          sparql: String(sparql || '').trim() || null,
          nl_mode: refs.nlMode.value || 'deterministic',
          extraction_mode: refs.extractionMode.value || 'deterministic',
          draft_edition: draftPayloadIfDirty(),
        };
        var result = await b.post(BASE + '/documents/' + encodeURIComponent(ctx.doc.id) + '/provenance-query', payload);
        state.queryResult = result;
        state.selectedTokens.clear();
        state.selectedRowIndex = -1;
        if (result.sparql) refs.sparqlInput.value = result.sparql;
        indexGraphData(state.graph, result);

        var ms = typeof result.execution_ms === 'number' ? result.execution_ms.toFixed(1) + ' ms' : '';
        var rowsCount = Array.isArray(result.rows) ? result.rows.length : 0;
        refs.queryMeta.textContent = rowsCount + ' fila(s)' + (ms ? ' · ' + ms : '') +
          (result.nl_compiler && result.nl_compiler !== 'none' ? ' · ' + result.nl_compiler : '');

        showWarnings(result.warnings || []);
        renderUnitSelector();
        renderResultsTable();
        renderSvgGraph();
        renderPassage(false);
        updateEdgeSummary();
      } catch (err) {
        showWarnings([err.message]);
        b.notify('Error en la consulta de proveniencia: ' + err.message, true);
      } finally {
        refs.sparqlRunBtn.disabled = false;
        refs.nlRunBtn.disabled = false;
      }
    }

    async function runVerifier() {
      var b = bridge();
      if (!b) return;
      var expr = refs.verifierInput.value.trim();
      if (!expr) {
        refs.verifierOutput.textContent = 'Introduce una expresión NPCS válida.';
        return;
      }
      refs.verifierBtn.disabled = true;
      try {
        var res = await b.post(BASE + '/provenance/polynomial/parse', { expression: expr });
        refs.verifierOutput.textContent =
          'Infijo N[X]: ' + res.infix + '\n' +
          'Compacto: ' + res.compact_infix + '\n' +
          'Prefijo NPCS: ' + res.npcs_prefix + '\n' +
          'Multiplicidad total: ' + res.total_multiplicity + '\n' +
          'Testigos: ' + (res.witness_tokens || []).join(', ');
      } catch (err) {
        refs.verifierOutput.textContent = 'Error: ' + err.message;
      } finally {
        refs.verifierBtn.disabled = false;
      }
    }

    async function exportNtriples() {
      var ctx = currentContext();
      var b = bridge();
      if (!ctx.doc || !b) return;
      var mode = encodeURIComponent(refs.extractionMode.value || 'deterministic');
      var url = BASE + '/documents/' + encodeURIComponent(ctx.doc.id) + '/provenance-graph/ntriples?mode=' + mode;
      try {
        var response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) throw new Error('Error HTTP ' + response.status);
        var text = await response.text();
        var blobUrl = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
        var a = el('a');
        a.href = blobUrl;
        a.download = ctx.doc.id.replace(/[^A-Za-z0-9._-]+/g, '-') + '-prov.nt';
        a.click();
        setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 1000);
      } catch (err) {
        b.notify('No se pudo exportar RDF-star: ' + err.message, true);
      }
    }

    function bindEvents() {
      refs.rebuildBtn.addEventListener('click', function () { void loadGraph(true); });
      refs.exportNtBtn.addEventListener('click', function () { void exportNtriples(); });
      refs.sparqlRunBtn.addEventListener('click', function () { void runQuery({ sparql: refs.sparqlInput.value, question: null }); });
      refs.nlRunBtn.addEventListener('click', function () { void runQuery({ sparql: '', question: refs.nlInput.value }); });
      refs.verifierBtn.addEventListener('click', function () { void runVerifier(); });

      refs.compactToggle.addEventListener('click', function () {
        state.compactMode = !state.compactMode;
        refs.compactToggle.setAttribute('aria-pressed', String(state.compactMode));
        refs.compactToggle.textContent = state.compactMode ? 'Compacto' : 'Exacto N[X]';
        renderResultsTable();
      });

      refs.npcsToggle.addEventListener('click', function () {
        state.showNpcs = !state.showNpcs;
        refs.npcsToggle.setAttribute('aria-pressed', String(state.showNpcs));
        renderResultsTable();
      });

      refs.clearSelBtn.addEventListener('click', function () {
        state.selectedRowIndex = -1;
        selectTokens([], { scrollPassage: false });
      });

      refs.zoomOutBtn.addEventListener('click', function () {
        state.zoom = Math.max(0.5, Number((state.zoom - 0.2).toFixed(2)));
        applySvgZoom();
      });
      refs.zoomInBtn.addEventListener('click', function () {
        state.zoom = Math.min(2.5, Number((state.zoom + 0.2).toFixed(2)));
        applySvgZoom();
      });
      refs.zoomResetBtn.addEventListener('click', function () {
        state.zoom = 1;
        applySvgZoom();
      });

      refs.unitSelect.addEventListener('change', function () {
        state.selectedUnitId = refs.unitSelect.value;
        updateJumpButtonState();
        renderPassage(false);
      });

      refs.jumpStructureBtn.addEventListener('click', function () {
        var b = bridge();
        if (b && state.selectedUnitId) {
          b.jumpToComponent(state.selectedUnitId);
        }
      });
    }

    mountShell();

    var b = bridge();
    if (b) {
      b.onTabActivated('provenance', function () {
        state.active = true;
        updateModePill();
        void loadGraph(false);
      });
      b.onTabActivated('*', function (_ctx, tab) {
        if (tab !== 'provenance') state.active = false;
      });
      b.onDocumentLoaded(function () {
        state.loadedDocSignature = '';
        state.graph = null;
        state.queryResult = null;
        state.selectedTokens.clear();
        updateModePill();
        if (state.active) void loadGraph(true);
      });
      b.onDraftChanged(function () {
        state.loadedDocSignature = '';
        updateModePill();
      });
    }

    return {
      loadGraph: loadGraph,
      runQuery: runQuery,
      selectTokens: selectTokens,
      getState: function () { return state; },
    };
  }

  function init() {
    var controller = createController();
    if (typeof window !== 'undefined' && controller) {
      window.SATGraphRAGProv = controller;
    }
  }

  if (document.getElementById('provenance-view')) {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  }
})();
