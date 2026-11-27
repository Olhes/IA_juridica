(function () {
  'use strict';

  var BASE = '/sat-graph/review/temporal';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  function bridge() {
    return typeof window !== 'undefined' ? window.SATReviewBridge : null;
  }

  function engine() {
    return typeof window !== 'undefined' ? window.SATTemporalEngine : null;
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

  function truncate(text, maxLen) {
    var s = String(text || '');
    return s.length > maxLen ? s.slice(0, maxLen - 1) + '…' : s;
  }

  function formatInterval(interval) {
    var start = Array.isArray(interval) && interval[0] ? interval[0] : null;
    var end = Array.isArray(interval) && interval[1] ? interval[1] : null;
    if (start === null && end === null) return '[null, null] · sin fecha legal';
    return '[' + (start || '−∞') + ', ' + (end || '+∞') + ')';
  }

  function createController() {
    var root = document.getElementById('temporal-view');
    if (!root) return null;

    var state = {
      sourceMode: 'active',
      samples: [],
      dataset: null,
      ticks: [],
      currentInstant: '2024-06-01T00:00:00Z',
      includeUnknownSnapshots: false,
      selectedItemId: '',
      selectedActionId: '',
      selectedVersionId: '',
      diffLeftId: '',
      diffRightId: '',
      loadedDocId: '',
      active: false,
    };

    var refs = {};

    function mountShell() {
      root.replaceChildren();
      var shell = el('div', undefined, 'ws-shell');

      var header = el('div', undefined, 'ws-header');
      var meta = el('div', undefined, 'ws-header-meta');
      meta.append(el('h2', 'SAT-Graph Viewer · Línea temporal normativa'));
      refs.datasetTitle = el('span', 'Sin conjunto temporal cargado', 'muted');
      refs.datasetTitle.id = 'temporal-dataset-title';
      meta.append(refs.datasetTitle);

      var sourceBar = el('div', undefined, 'temporal-source-bar');
      refs.srcActiveBtn = el('button', 'Norma activa');
      refs.srcActiveBtn.type = 'button';
      refs.srcActiveBtn.id = 'temporal-src-active';
      refs.srcActiveBtn.setAttribute('aria-pressed', 'true');

      refs.srcCorpusBtn = el('button', 'Corpus completo');
      refs.srcCorpusBtn.type = 'button';
      refs.srcCorpusBtn.id = 'temporal-src-corpus';
      refs.srcCorpusBtn.setAttribute('aria-pressed', 'false');

      refs.srcSamplesBtn = el('button', 'Ejemplos SAT-Graph');
      refs.srcSamplesBtn.type = 'button';
      refs.srcSamplesBtn.id = 'temporal-src-samples';
      refs.srcSamplesBtn.setAttribute('aria-pressed', 'false');

      refs.sampleSelect = el('select');
      refs.sampleSelect.id = 'temporal-sample-select';
      refs.sampleSelect.setAttribute('aria-label', 'Seleccionar ejemplo SAT-Graph');
      refs.sampleSelect.hidden = true;

      var fileLabel = el('label', 'Cargar JSON SAT-Graph', 'ws-file-btn');
      refs.fileInput = el('input', undefined, 'ws-sr-only');
      refs.fileInput.id = 'temporal-file-input';
      refs.fileInput.type = 'file';
      refs.fileInput.accept = '.json,application/json';
      fileLabel.append(refs.fileInput);

      sourceBar.append(refs.srcActiveBtn, refs.srcCorpusBtn, refs.srcSamplesBtn, refs.sampleSelect, fileLabel);
      header.append(meta, sourceBar);
      shell.append(header);

      refs.validationBanner = el('div', undefined, 'ws-banner ws-banner-error');
      refs.validationBanner.id = 'temporal-validation-banner';
      refs.validationBanner.setAttribute('role', 'alert');
      refs.validationBanner.hidden = true;
      shell.append(refs.validationBanner);

      refs.policyBanner = el('div', 'Las versiones con validityInterval [null, null] representan capturas verificadas del corpus sin fecha legal sintetizada.', 'ws-banner');
      refs.policyBanner.id = 'temporal-policy-banner';
      shell.append(refs.policyBanner);

      var ctrlCard = el('div', undefined, 'ws-card');
      var ctrlGrid = el('div', undefined, 'temporal-controls-grid');

      var leftCol = el('div', undefined, 'prov-query-box');
      var instantRow = el('div', undefined, 'temporal-instant-row');
      var instLabel = el('label', 'Instante de consulta (RFC 3339 o YYYY-MM-DD)');
      instLabel.setAttribute('for', 'temporal-instant-input');
      refs.instantInput = el('input');
      refs.instantInput.id = 'temporal-instant-input';
      refs.instantInput.type = 'text';
      refs.instantInput.value = state.currentInstant;
      instLabel.append(refs.instantInput);

      refs.instantApplyBtn = el('button', 'Aplicar instante', 'primary');
      refs.instantApplyBtn.type = 'button';
      refs.instantApplyBtn.id = 'temporal-instant-apply';
      instantRow.append(instLabel, refs.instantApplyBtn);
      leftCol.append(instantRow);

      refs.instantError = el('div', undefined, 'ws-banner ws-banner-error');
      refs.instantError.id = 'temporal-instant-error';
      refs.instantError.setAttribute('role', 'alert');
      refs.instantError.hidden = true;
      leftCol.append(refs.instantError);

      var probeRow = el('div', undefined, 'temporal-probe-row');
      refs.prevTransBtn = el('button', '◀ Transición');
      refs.prevTransBtn.type = 'button';
      refs.prevTransBtn.id = 'temporal-prev-transition';
      refs.nextTransBtn = el('button', 'Transición ▶');
      refs.nextTransBtn.type = 'button';
      refs.nextTransBtn.id = 'temporal-next-transition';
      refs.minusSBtn = el('button', '−1s');
      refs.minusSBtn.type = 'button';
      refs.minusSBtn.id = 'temporal-step-minus-s';
      refs.plusSBtn = el('button', '+1s');
      refs.plusSBtn.type = 'button';
      refs.plusSBtn.id = 'temporal-step-plus-s';
      refs.minusMsBtn = el('button', '−1ms');
      refs.minusMsBtn.type = 'button';
      refs.minusMsBtn.id = 'temporal-step-minus-ms';
      refs.plusMsBtn = el('button', '+1ms');
      refs.plusMsBtn.type = 'button';
      refs.plusMsBtn.id = 'temporal-step-plus-ms';
      probeRow.append(
        refs.prevTransBtn, refs.nextTransBtn,
        refs.minusSBtn, refs.plusSBtn,
        refs.minusMsBtn, refs.plusMsBtn
      );
      leftCol.append(probeRow);

      var unknownLabel = el('label', undefined, 'temporal-checkbox-label');
      refs.includeUnknown = el('input');
      refs.includeUnknown.id = 'temporal-include-unknown';
      refs.includeUnknown.type = 'checkbox';
      unknownLabel.append(refs.includeUnknown, document.createTextNode('Mostrar snapshots sin fecha legal [null, null]'));
      leftCol.append(unknownLabel);

      var sliderWrap = el('div', undefined, 'temporal-slider-wrap');
      var sliderHead = el('div', undefined, 'temporal-slider-head');
      var sliderLabel = el('label', 'Hitos de la línea temporal');
      sliderLabel.setAttribute('for', 'temporal-slider');
      refs.sliderReadout = el('span', state.currentInstant, 'muted');
      refs.sliderReadout.id = 'temporal-slider-readout';
      sliderHead.append(sliderLabel, refs.sliderReadout);

      refs.slider = el('input', undefined, 'temporal-range-input');
      refs.slider.id = 'temporal-slider';
      refs.slider.type = 'range';
      refs.slider.min = '0';
      refs.slider.max = '0';
      refs.slider.step = '1';
      refs.slider.value = '0';
      refs.slider.setAttribute('aria-valuetext', state.currentInstant);
      sliderWrap.append(sliderHead, refs.slider);

      ctrlGrid.append(leftCol, sliderWrap);
      ctrlCard.append(ctrlGrid);
      shell.append(ctrlCard);

      var svgCard = el('div', undefined, 'ws-card');
      var svgHead = el('div', undefined, 'ws-card-head');
      svgHead.append(el('h3', 'Línea temporal de versiones [inicio, fin) y acciones causales'));
      var legend = el('div', undefined, 'temporal-legend');
      var legItems = [
        ['temporal-swatch-stv', 'Normativa (S-TV)'],
        ['temporal-swatch-itv', 'Interpretativa (I-TV)'],
        ['temporal-swatch-unknown', 'Captura [null, null]'],
      ];
      for (var li = 0; li < legItems.length; li++) {
        var span = el('span');
        span.append(el('span', undefined, 'temporal-swatch ' + legItems[li][0]), document.createTextNode(legItems[li][1]));
        legend.append(span);
      }
      svgHead.append(legend);
      svgCard.append(svgHead);

      var svgScroll = el('div', undefined, 'temporal-svg-scroll');
      refs.timelineSvg = svgEl('svg', {
        id: 'temporal-timeline-svg',
        class: 'temporal-svg',
        viewBox: '0 0 860 220',
        role: 'img',
        'aria-label': 'Línea temporal de versiones y acciones SAT-Graph',
      });
      svgScroll.append(refs.timelineSvg);
      svgCard.append(svgScroll);
      shell.append(svgCard);

      var panelsGrid = el('div', undefined, 'temporal-panels-grid');

      var stvCard = el('div', undefined, 'ws-card');
      var stvHead = el('div', undefined, 'ws-card-head');
      stvHead.append(el('h3', 'Normativo vigente (S-TV)'));
      refs.stvCount = el('span', '0', 'ws-badge');
      stvHead.append(refs.stvCount);
      refs.stvList = el('div', undefined, 'temporal-version-list');
      refs.stvList.id = 'temporal-statutory-list';
      stvCard.append(stvHead, refs.stvList);

      var itvCard = el('div', undefined, 'ws-card');
      var itvHead = el('div', undefined, 'ws-card-head');
      itvHead.append(el('h3', 'Interpretativo (I-TV)'));
      refs.itvCount = el('span', '0', 'ws-badge');
      itvHead.append(refs.itvCount);
      refs.itvList = el('div', undefined, 'temporal-version-list');
      refs.itvList.id = 'temporal-interpretive-list';
      itvCard.append(itvHead, refs.itvList);

      panelsGrid.append(stvCard, itvCard);
      shell.append(panelsGrid);

      var diffCard = el('div', undefined, 'ws-card');
      var diffHead = el('div', undefined, 'ws-card-head');
      diffHead.append(el('h3', 'Diff entre versiones'));
      refs.diffSummary = el('span', 'Selecciona dos versiones o haz clic en una acción causal de la línea temporal.', 'muted');
      diffHead.append(refs.diffSummary);
      diffCard.append(diffHead);

      var diffControls = el('div', undefined, 'temporal-diff-controls');
      var leftDiffLabel = el('label', 'Versión base (anterior)');
      leftDiffLabel.setAttribute('for', 'temporal-diff-left');
      refs.diffLeftSelect = el('select');
      refs.diffLeftSelect.id = 'temporal-diff-left';
      leftDiffLabel.append(refs.diffLeftSelect);

      var rightDiffLabel = el('label', 'Versión destino (posterior)');
      rightDiffLabel.setAttribute('for', 'temporal-diff-right');
      refs.diffRightSelect = el('select');
      refs.diffRightSelect.id = 'temporal-diff-right';
      rightDiffLabel.append(refs.diffRightSelect);

      diffControls.append(leftDiffLabel, rightDiffLabel);
      diffCard.append(diffControls);

      refs.diffOutput = el('div', 'Selecciona dos versiones para comparar sus textos.', 'temporal-diff-box');
      refs.diffOutput.id = 'temporal-diff-output';
      diffCard.append(refs.diffOutput);
      shell.append(diffCard);

      var rawDetails = el('details', undefined, 'prov-verifier-details');
      rawDetails.id = 'temporal-raw-details';
      rawDetails.append(el('summary', 'Inspección JSON cruda · getValidVersions(at) y getItemHistory(item)'));

      var rawControls = el('div', undefined, 'ws-inline-controls');
      var itemSelLabel = el('label', 'Elemento para historial', 'ws-sr-only');
      itemSelLabel.setAttribute('for', 'temporal-history-item-select');
      refs.historyItemSelect = el('select');
      refs.historyItemSelect.id = 'temporal-history-item-select';
      refs.historyItemSelect.setAttribute('aria-label', 'Elemento SAT para getItemHistory');
      refs.copyJsonBtn = el('button', 'Copiar JSON');
      refs.copyJsonBtn.type = 'button';
      refs.copyJsonBtn.id = 'temporal-copy-json-btn';
      rawControls.append(itemSelLabel, refs.historyItemSelect, refs.copyJsonBtn);
      rawDetails.append(rawControls);

      var rawGrid = el('div', undefined, 'temporal-raw-grid');
      var rawValidCol = el('div');
      rawValidCol.append(el('strong', 'getValidVersions(at)'));
      refs.rawValidPre = el('pre', '[]', 'temporal-raw-pre');
      refs.rawValidPre.id = 'temporal-raw-valid-json';
      rawValidCol.append(refs.rawValidPre);

      var rawHistCol = el('div');
      rawHistCol.append(el('strong', 'getItemHistory(item)'));
      refs.rawHistoryPre = el('pre', '[]', 'temporal-raw-pre');
      refs.rawHistoryPre.id = 'temporal-raw-history-json';
      rawHistCol.append(refs.rawHistoryPre);

      rawGrid.append(rawValidCol, rawHistCol);
      rawDetails.append(rawGrid);
      shell.append(rawDetails);

      root.append(shell);
      syncSliderCustomProperties();
      bindEvents();
    }

    function syncSliderCustomProperties() {
      var minVal = refs.slider.min !== '' ? refs.slider.min : '0';
      var maxVal = refs.slider.max !== '' ? refs.slider.max : '0';
      refs.slider.style.setProperty('--attr-min', minVal);
      refs.slider.style.setProperty('--attr-max', maxVal);
      refs.slider.style.setProperty('--control-value', refs.slider.value || '0');
    }

    function updateSourceButtons() {
      refs.srcActiveBtn.setAttribute('aria-pressed', String(state.sourceMode === 'active'));
      refs.srcCorpusBtn.setAttribute('aria-pressed', String(state.sourceMode === 'corpus'));
      refs.srcSamplesBtn.setAttribute('aria-pressed', String(state.sourceMode === 'samples'));
      refs.sampleSelect.hidden = state.sourceMode !== 'samples' || !state.samples.length;
    }

    function showValidation(errors, warnings) {
      var errs = Array.isArray(errors) ? errors : [];
      var warns = Array.isArray(warnings) ? warnings : [];
      if (errs.length) {
        refs.validationBanner.className = 'ws-banner ws-banner-error';
        refs.validationBanner.hidden = false;
        refs.validationBanner.textContent = 'JSON SAT-Graph inválido: ' + errs.map(function (e) {
          return '[' + e.code + '] ' + e.message;
        }).join(' · ');
      } else if (warns.length) {
        refs.validationBanner.className = 'ws-banner ws-banner-warn';
        refs.validationBanner.hidden = false;
        refs.validationBanner.textContent = 'Advertencias de validación (' + warns.length + '): ' + warns.slice(0, 3).map(function (w) {
          return w.message;
        }).join(' · ');
      } else {
        refs.validationBanner.hidden = true;
        refs.validationBanner.textContent = '';
      }
    }

    function textForVersion(versionId) {
      if (!state.dataset) return '';
      var units = state.dataset.textUnits || [];
      for (var i = 0; i < units.length; i++) {
        if (units[i].sourceId === versionId) return units[i].content || '';
      }
      return '';
    }

    function orderedItemsWithDepth(items) {
      var byParent = new Map();
      var byId = new Map();
      for (var i = 0; i < items.length; i++) {
        byId.set(items[i].id, items[i]);
      }
      for (var j = 0; j < items.length; j++) {
        var pid = items[j].parentId && byId.has(items[j].parentId) ? items[j].parentId : '';
        if (!byParent.has(pid)) byParent.set(pid, []);
        byParent.get(pid).push(items[j]);
      }
      var result = [];
      var visited = new Set();
      function walk(parentId, depth) {
        var children = byParent.get(parentId) || [];
        for (var k = 0; k < children.length; k++) {
          var item = children[k];
          if (visited.has(item.id)) continue;
          visited.add(item.id);
          result.push({ item: item, depth: depth });
          walk(item.id, depth + 1);
        }
      }
      walk('', 0);
      for (var r = 0; r < items.length; r++) {
        if (!visited.has(items[r].id)) {
          result.push({ item: items[r], depth: 0 });
        }
      }
      return result;
    }

    function applyDataset(rawDataset, validationWarnings) {
      var eng = engine();
      if (!eng) return;
      var norm = eng.normalizeDataset(rawDataset);
      state.dataset = norm;
      state.ticks = eng.collectTimelineTicks(norm);
      state.selectedActionId = '';
      state.selectedVersionId = '';

      refs.datasetTitle.textContent = norm.title || norm.resourceId || 'Conjunto SAT-Graph';

      var knownCount = norm.versions.filter(function (v) {
        return v.validityInterval[0] !== null || v.validityInterval[1] !== null;
      }).length;
      var unknownCount = norm.versions.length - knownCount;
      var editorialCount = norm.actions.filter(function (a) { return a.kind === 'editorial_revision'; }).length;
      var normativeCount = norm.actions.length - editorialCount;

      var policyParts = [];
      if (norm.policyNote) policyParts.push(norm.policyNote);
      policyParts.push(
        'Intervalos legales verificados: ' + knownCount +
        ' · Snapshots [null, null] sin fecha legal: ' + unknownCount +
        ' · Acciones normativas: ' + normativeCount +
        ' · Revisiones editoriales: ' + editorialCount + '.'
      );
      refs.policyBanner.textContent = policyParts.join(' ');
      refs.policyBanner.className = unknownCount > 0 && knownCount === 0
        ? 'ws-banner ws-banner-warn'
        : 'ws-banner';

      showValidation([], validationWarnings || []);

      if (state.ticks.length) {
        var initialTick = state.ticks[state.ticks.length - 1];
        state.currentInstant = initialTick.iso;
        refs.slider.min = '0';
        refs.slider.max = String(state.ticks.length - 1);
        refs.slider.value = String(state.ticks.length - 1);
        refs.slider.disabled = state.ticks.length <= 1;
      } else {
        refs.slider.min = '0';
        refs.slider.max = '0';
        refs.slider.value = '0';
        refs.slider.disabled = true;
      }
      refs.instantInput.value = state.currentInstant;
      refs.instantError.hidden = true;

      refs.historyItemSelect.replaceChildren();
      var ordered = orderedItemsWithDepth(norm.items);
      for (var ii = 0; ii < ordered.length; ii++) {
        var opt = el('option', '  '.repeat(ordered[ii].depth) + (ordered[ii].item.label || ordered[ii].item.id));
        opt.value = ordered[ii].item.id;
        refs.historyItemSelect.append(opt);
      }
      var itemWithVersions = norm.versions[0] ? norm.versions[0].itemId : (ordered[0] ? ordered[0].item.id : '');
      state.selectedItemId = itemWithVersions;
      if (state.selectedItemId) refs.historyItemSelect.value = state.selectedItemId;

      populateDiffSelects(norm.versions);
      syncSliderReadout();
      renderAllViews();
    }

    function populateDiffSelects(versions) {
      refs.diffLeftSelect.replaceChildren();
      refs.diffRightSelect.replaceChildren();
      if (!versions.length) {
        state.diffLeftId = '';
        state.diffRightId = '';
        return;
      }
      for (var i = 0; i < versions.length; i++) {
        var v = versions[i];
        var label = v.id + ' (' + v.type + ' · ' + formatInterval(v.validityInterval) + ')';
        var optL = el('option', label);
        optL.value = v.id;
        var optR = el('option', label);
        optR.value = v.id;
        refs.diffLeftSelect.append(optL);
        refs.diffRightSelect.append(optR);
      }
      state.diffLeftId = versions[0].id;
      state.diffRightId = versions.length > 1 ? versions[versions.length - 1].id : versions[0].id;
      refs.diffLeftSelect.value = state.diffLeftId;
      refs.diffRightSelect.value = state.diffRightId;
    }

    function syncSliderReadout() {
      var eng = engine();
      if (state.ticks.length && eng) {
        var curMs;
        try { curMs = eng.parseInstantMs(state.currentInstant); } catch (_e) { curMs = null; }
        if (curMs !== null) {
          var bestIdx = 0;
          var bestDist = Infinity;
          for (var i = 0; i < state.ticks.length; i++) {
            var dist = Math.abs(state.ticks[i].ms - curMs);
            if (dist < bestDist) {
              bestDist = dist;
              bestIdx = i;
            }
          }
          refs.slider.value = String(bestIdx);
        }
      }
      var idx = Number(refs.slider.value) || 0;
      var tick = state.ticks[idx];
      var valueText = tick
        ? state.currentInstant + ' · ' + tick.label
        : state.currentInstant;
      refs.slider.setAttribute('aria-valuetext', valueText);
      refs.sliderReadout.textContent = valueText;
      syncSliderCustomProperties();
    }

    function setInstant(rawInstant) {
      var eng = engine();
      if (!eng) return false;
      try {
        var normalized = eng.normalizeInstantISO(rawInstant);
        state.currentInstant = normalized;
        refs.instantInput.value = normalized;
        refs.instantError.hidden = true;
        refs.instantError.textContent = '';
        syncSliderReadout();
        renderAllViews();
        return true;
      } catch (err) {
        refs.instantError.hidden = false;
        refs.instantError.textContent = 'Instante inválido: ' + err.message;
        return false;
      }
    }

    function stepInstantByMs(deltaMs) {
      var eng = engine();
      if (!eng) return;
      try {
        var curMs = eng.parseInstantMs(state.currentInstant);
        var nextIso = new Date(curMs + deltaMs).toISOString();
        setInstant(nextIso.endsWith('.000Z') ? nextIso.replace('.000Z', 'Z') : nextIso);
      } catch (_err) {
      }
    }

    function stepTransition(direction) {
      var eng = engine();
      if (!eng || !state.ticks.length) return;
      var curMs;
      try { curMs = eng.parseInstantMs(state.currentInstant); } catch (_err) { return; }
      if (direction < 0) {
        for (var i = state.ticks.length - 1; i >= 0; i--) {
          if (state.ticks[i].ms < curMs) {
            setInstant(state.ticks[i].iso);
            return;
          }
        }
        setInstant(state.ticks[0].iso);
      } else {
        for (var j = 0; j < state.ticks.length; j++) {
          if (state.ticks[j].ms > curMs) {
            setInstant(state.ticks[j].iso);
            return;
          }
        }
        setInstant(state.ticks[state.ticks.length - 1].iso);
      }
    }

    function renderTimelineSvg() {
      refs.timelineSvg.replaceChildren();
      var ds = state.dataset;
      var eng = engine();
      if (!ds || !eng) return;

      var ordered = orderedItemsWithDepth(ds.items);
      if (!ordered.length) {
        var emptyMsg = svgEl('text', { x: 430, y: 110, 'text-anchor': 'middle', class: 'temporal-axis-label' });
        emptyMsg.textContent = 'Este conjunto no contiene elementos (Items) para graficar.';
        refs.timelineSvg.append(emptyMsg);
        return;
      }

      var leftColW = 240;
      var rightPad = 30;
      var plotW = 590;
      var svgW = leftColW + plotW + rightPad;
      var topPad = 36;
      var laneH = 44;
      var svgH = Math.max(190, topPad + ordered.length * laneH + 26);
      refs.timelineSvg.setAttribute('viewBox', '0 0 ' + svgW + ' ' + svgH);

      var timestamps = [];
      for (var ti = 0; ti < state.ticks.length; ti++) {
        timestamps.push(state.ticks[ti].ms);
      }
      var queryMs;
      try { queryMs = eng.parseInstantMs(state.currentInstant); } catch (_e) { queryMs = null; }
      if (queryMs !== null) timestamps.push(queryMs);

      var minMs = timestamps.length ? Math.min.apply(null, timestamps) : Date.UTC(2020, 0, 1);
      var maxMs = timestamps.length ? Math.max.apply(null, timestamps) : Date.UTC(2026, 0, 1);
      if (maxMs <= minMs) {
        var halfYear = 180 * 86400000;
        minMs -= halfYear;
        maxMs += halfYear;
      } else {
        var span = maxMs - minMs;
        minMs -= Math.round(span * 0.06);
        maxMs += Math.round(span * 0.12);
      }

      function xOf(ms) {
        return leftColW + ((ms - minMs) / (maxMs - minMs)) * plotW;
      }

      var axisSteps = 4;
      for (var a = 0; a <= axisSteps; a++) {
        var tMs = minMs + ((maxMs - minMs) * a) / axisSteps;
        var ax = xOf(tMs);
        refs.timelineSvg.append(svgEl('line', {
          x1: ax.toFixed(1),
          y1: topPad - 8,
          x2: ax.toFixed(1),
          y2: svgH - 12,
          stroke: 'var(--line)',
          'stroke-width': 1,
        }));
        var lbl = svgEl('text', { x: ax.toFixed(1), y: 20, 'text-anchor': 'middle', class: 'temporal-axis-label' });
        lbl.textContent = new Date(tMs).toISOString().slice(0, 10);
        refs.timelineSvg.append(lbl);
      }

      var laneCenterByItem = new Map();
      var versionsByItem = new Map();
      for (var vi = 0; vi < ds.versions.length; vi++) {
        var ver = ds.versions[vi];
        if (!versionsByItem.has(ver.itemId)) versionsByItem.set(ver.itemId, []);
        versionsByItem.get(ver.itemId).push(ver);
      }

      var versionCoords = new Map();

      for (var li = 0; li < ordered.length; li++) {
        var entry = ordered[li];
        var laneY = topPad + li * laneH;
        laneCenterByItem.set(entry.item.id, laneY + laneH / 2);

        refs.timelineSvg.append(svgEl('rect', {
          x: 0,
          y: laneY,
          width: svgW,
          height: laneH,
          class: 'temporal-lane-bg' + (li % 2 === 1 ? ' temporal-lane-alt' : ''),
        }));

        var itemLabel = svgEl('text', {
          x: 10 + Math.min(entry.depth, 5) * 14,
          y: laneY + 26,
          class: 'temporal-lane-label',
        });
        itemLabel.textContent = truncate(entry.item.label || entry.item.id, 30 - Math.min(entry.depth, 4) * 2);
        var itemTitle = svgEl('title');
        itemTitle.textContent = (entry.item.label || entry.item.id) + ' (' + entry.item.typeId + ')';
        itemLabel.append(itemTitle);
        refs.timelineSvg.append(itemLabel);

        var itemVersions = versionsByItem.get(entry.item.id) || [];
        var itvSlot = 0;
        for (var vj = 0; vj < itemVersions.length; vj++) {
          (function (v) {
            var startIso = v.validityInterval[0];
            var endIso = v.validityInterval[1];
            var isUnknown = startIso === null && endIso === null;
            var isSelected = state.selectedVersionId === v.id;

            if (isUnknown) {
              var snapMs = v.metadata && v.metadata.snapshotAsOf
                ? (function () { try { return eng.parseInstantMs(v.metadata.snapshotAsOf); } catch (_e) { return null; } })()
                : null;
              var cx = snapMs !== null ? xOf(snapMs) : (leftColW + plotW * 0.5);
              var cy = laneY + laneH / 2;
              versionCoords.set(v.id, { x: cx, y: cy });
              var dPts = [
                cx.toFixed(1) + ',' + (cy - 7).toFixed(1),
                (cx + 7).toFixed(1) + ',' + cy.toFixed(1),
                cx.toFixed(1) + ',' + (cy + 7).toFixed(1),
                (cx - 7).toFixed(1) + ',' + cy.toFixed(1),
              ].join(' ');
              var poly = svgEl('polygon', {
                points: dPts,
                class: 'temporal-bar temporal-bar-unknown' + (isSelected ? ' temporal-selected' : ''),
                'data-version-id': v.id,
                tabindex: '0',
                role: 'button',
                'aria-label': 'Snapshot sin fecha legal ' + v.id,
              });
              var vt = svgEl('title');
              vt.textContent = v.id + ' · [null, null] sin fecha legal (legalIntervalKnown: false)';
              poly.append(vt);
              poly.addEventListener('click', function () { selectVersion(v); });
              refs.timelineSvg.append(poly);
              return;
            }

            var sMs = startIso !== null ? eng.parseInstantMs(startIso) : minMs;
            var eMs = endIso !== null ? eng.parseInstantMs(endIso) : maxMs;
            var x1 = xOf(sMs);
            var x2 = Math.max(x1 + 8, xOf(eMs));
            var barY;
            var barH;
            var barCls;
            if (v.type === 'interpretive') {
              barY = laneY + 24 + (itvSlot % 2) * 8;
              barH = 9;
              barCls = 'temporal-bar temporal-bar-itv';
              itvSlot++;
            } else {
              barY = laneY + 8;
              barH = 13;
              barCls = 'temporal-bar temporal-bar-stv';
            }
            versionCoords.set(v.id, { x: (x1 + x2) / 2, y: barY + barH / 2, x1: x1, x2: x2 });

            var rect = svgEl('rect', {
              x: x1.toFixed(1),
              y: barY.toFixed(1),
              width: (x2 - x1).toFixed(1),
              height: barH,
              rx: 3,
              class: barCls + (isSelected ? ' temporal-selected' : ''),
              'data-version-id': v.id,
              tabindex: '0',
              role: 'button',
              'aria-label': v.id + ' ' + formatInterval(v.validityInterval),
            });
            var rt = svgEl('title');
            rt.textContent = v.id + ' (' + v.type + ') · ' + formatInterval(v.validityInterval);
            rect.append(rt);
            rect.addEventListener('click', function () { selectVersion(v); });
            refs.timelineSvg.append(rect);
          })(itemVersions[vj]);
        }
      }

      var actions = ds.actions || [];
      for (var ai = 0; ai < actions.length; ai++) {
        (function (act) {
          if (!act.eventTime) return;
          var actMs;
          try { actMs = eng.parseInstantMs(act.eventTime); } catch (_e) { return; }
          var ax = xOf(actMs);
          var ay = topPad - 6;

          for (var t = 0; t < act.terminatesVersionIds.length; t++) {
            var tc = versionCoords.get(act.terminatesVersionIds[t]);
            if (tc) {
              refs.timelineSvg.append(svgEl('path', {
                d: 'M ' + ax.toFixed(1) + ' ' + ay.toFixed(1) + ' Q ' + ax.toFixed(1) + ' ' + tc.y.toFixed(1) + ' ' + (tc.x2 || tc.x).toFixed(1) + ' ' + tc.y.toFixed(1),
                class: 'temporal-connector-term',
              }));
            }
          }
          for (var p = 0; p < act.producesVersionIds.length; p++) {
            var pc = versionCoords.get(act.producesVersionIds[p]);
            if (pc) {
              refs.timelineSvg.append(svgEl('path', {
                d: 'M ' + ax.toFixed(1) + ' ' + ay.toFixed(1) + ' Q ' + ax.toFixed(1) + ' ' + pc.y.toFixed(1) + ' ' + (pc.x1 || pc.x).toFixed(1) + ' ' + pc.y.toFixed(1),
                class: 'temporal-connector-prod',
              }));
            }
          }

          var g = svgEl('g', {
            class: 'temporal-action-marker' +
              (act.kind === 'editorial_revision' ? ' temporal-action-editorial' : '') +
              (state.selectedActionId === act.id ? ' temporal-selected' : ''),
            'data-action-id': act.id,
            tabindex: '0',
            role: 'button',
            'aria-label': (act.label || act.kind) + ' · ' + act.eventTime,
          });
          var title = svgEl('title');
          title.textContent = act.kind + ': ' + (act.label || act.id) + ' (' + act.eventTime + ')';
          g.append(title);
          g.append(svgEl('circle', { cx: ax.toFixed(1), cy: ay.toFixed(1), r: 5.5 }));
          var activateAction = function () {
            state.selectedActionId = act.id;
            if (act.terminatesVersionIds.length && act.producesVersionIds.length) {
              state.diffLeftId = act.terminatesVersionIds[0];
              state.diffRightId = act.producesVersionIds[0];
              refs.diffLeftSelect.value = state.diffLeftId;
              refs.diffRightSelect.value = state.diffRightId;
              renderDiffPanel();
            }
            setInstant(act.eventTime);
          };
          g.addEventListener('click', activateAction);
          g.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              activateAction();
            }
          });
          refs.timelineSvg.append(g);
        })(actions[ai]);
      }

      if (queryMs !== null) {
        var qx = xOf(queryMs);
        refs.timelineSvg.append(svgEl('line', {
          x1: qx.toFixed(1),
          y1: topPad - 12,
          x2: qx.toFixed(1),
          y2: svgH - 8,
          class: 'temporal-cursor',
        }));
      }
    }

    function selectVersion(version) {
      state.selectedVersionId = version.id;
      state.selectedItemId = version.itemId;
      if (refs.historyItemSelect) refs.historyItemSelect.value = version.itemId;
      renderTimelineSvg();
      renderRawInspector();
    }

    function renderVersionPanels() {
      var ds = state.dataset;
      var eng = engine();
      refs.stvList.replaceChildren();
      refs.itvList.replaceChildren();
      if (!ds || !eng) return;

      var valid;
      try {
        valid = eng.getValidVersions(ds, state.currentInstant, {
          includeUnknownSnapshots: state.includeUnknownSnapshots,
        });
      } catch (_err) {
        valid = [];
      }

      var itemLabelById = new Map();
      for (var i = 0; i < ds.items.length; i++) {
        itemLabelById.set(ds.items[i].id, ds.items[i].label || ds.items[i].id);
      }

      var stv = valid.filter(function (v) { return v.type === 'statutory'; });
      var itv = valid.filter(function (v) { return v.type === 'interpretive'; });

      refs.stvCount.textContent = String(stv.length);
      refs.itvCount.textContent = String(itv.length);

      function renderCards(container, list, kindClass, emptyText) {
        if (!list.length) {
          container.append(el('p', emptyText, 'muted'));
          return;
        }
        for (var idx = 0; idx < list.length; idx++) {
          var v = list[idx];
          var card = el('article', undefined, 'temporal-version-card ' + kindClass);
          card.dataset.versionId = v.id;
          card.append(el('strong', itemLabelById.get(v.itemId) || v.itemId));
          var metaRow = el('div', undefined, 'temporal-version-meta');
          metaRow.append(
            el('span', v.id, 'ws-badge'),
            el('span', formatInterval(v.validityInterval))
          );
          if (v.metadata && v.metadata.authority) {
            metaRow.append(el('span', v.metadata.authority, 'ws-badge'));
          }
          if (v.metadata && v.metadata.legalIntervalKnown === false) {
            metaRow.append(el('span', 'Sin fecha legal', 'ws-badge ws-badge-draft'));
          }
          if (v.metadata && v.metadata.archived) {
            metaRow.append(el('span', 'Archivada', 'ws-badge'));
          }
          card.append(metaRow);
          var txt = textForVersion(v.id);
          card.append(el('p', txt || '(Sin TextUnit asociado)', 'temporal-version-text'));
          container.append(card);
        }
      }

      renderCards(
        refs.stvList,
        stv,
        'temporal-version-card-stv',
        state.includeUnknownSnapshots
          ? 'No hay versiones normativas vigentes en este instante.'
          : 'No hay versiones normativas con intervalo legal vigente en este instante. Activa «Mostrar snapshots sin fecha legal» si el corpus tiene capturas [null, null].'
      );
      renderCards(
        refs.itvList,
        itv,
        'temporal-version-card-itv',
        'No hay versiones interpretativas (I-TV) vigentes en este instante.'
      );
    }

    function renderDiffPanel() {
      refs.diffOutput.replaceChildren();
      var eng = engine();
      if (!state.dataset || !eng || !state.diffLeftId || !state.diffRightId) {
        refs.diffOutput.textContent = 'Selecciona dos versiones para comparar sus textos.';
        return;
      }
      var leftText = textForVersion(state.diffLeftId);
      var rightText = textForVersion(state.diffRightId);
      var ops = eng.diffVersionTexts(leftText, rightText);
      var delCount = 0;
      var insCount = 0;
      var frag = document.createDocumentFragment();
      for (var i = 0; i < ops.length; i++) {
        var op = ops[i];
        if (op.op === 'delete') {
          delCount++;
          frag.append(el('del', op.text, 'temporal-diff-del'));
        } else if (op.op === 'insert') {
          insCount++;
          frag.append(el('ins', op.text, 'temporal-diff-ins'));
        } else {
          frag.append(el('span', op.text));
        }
      }
      refs.diffOutput.append(frag);
      refs.diffSummary.textContent = state.diffLeftId + ' → ' + state.diffRightId +
        ' (' + delCount + ' eliminación(es), ' + insCount + ' inserción(es))';
    }

    function renderRawInspector() {
      var ds = state.dataset;
      var eng = engine();
      if (!ds || !eng) return;
      var valid;
      try {
        valid = eng.getValidVersions(ds, state.currentInstant, {
          includeUnknownSnapshots: state.includeUnknownSnapshots,
        });
      } catch (_e) {
        valid = [];
      }
      refs.rawValidPre.textContent = JSON.stringify(valid, null, 2);

      var hist = state.selectedItemId ? eng.getItemHistory(ds, state.selectedItemId) : [];
      refs.rawHistoryPre.textContent = JSON.stringify(hist, null, 2);
      state.lastRawSnapshot = {
        at: state.currentInstant,
        validVersions: valid,
        itemHistory: hist,
      };
    }

    function renderAllViews() {
      renderTimelineSvg();
      renderVersionPanels();
      renderDiffPanel();
      renderRawInspector();
    }

    async function loadActiveDocumentDataset() {
      var b = bridge();
      var ctx = b ? b.getContext() : null;
      if (!b || !ctx || !ctx.doc) return;
      state.sourceMode = 'active';
      updateSourceButtons();
      try {
        var ds = await b.request(BASE + '/dataset/' + encodeURIComponent(ctx.doc.id));
        state.loadedDocId = ctx.doc.id;
        applyDataset(ds);
      } catch (err) {
        b.notify('No se pudo cargar la línea temporal del documento: ' + err.message, true);
      }
    }

    async function loadCorpusDataset() {
      var b = bridge();
      if (!b) return;
      state.sourceMode = 'corpus';
      updateSourceButtons();
      try {
        var ds = await b.request(BASE + '/dataset');
        applyDataset(ds);
      } catch (err) {
        b.notify('No se pudo cargar la línea temporal del corpus completo: ' + err.message, true);
      }
    }

    async function loadSamples() {
      var b = bridge();
      if (!b) return;
      state.sourceMode = 'samples';
      try {
        if (!state.samples.length) {
          var res = await b.request(BASE + '/samples');
          state.samples = Array.isArray(res.samples) ? res.samples : [];
          refs.sampleSelect.replaceChildren();
          for (var i = 0; i < state.samples.length; i++) {
            var sample = state.samples[i];
            var opt = el('option', sample.title || sample.id);
            opt.value = sample.id;
            refs.sampleSelect.append(opt);
          }
        }
        updateSourceButtons();
        if (state.samples.length) {
          var chosenId = refs.sampleSelect.value || state.samples[0].id;
          refs.sampleSelect.value = chosenId;
          var chosen = state.samples.find(function (s) { return s.id === chosenId; }) || state.samples[0];
          if (chosen && chosen.dataset) applyDataset(chosen.dataset);
        }
      } catch (err) {
        b.notify('No se pudieron cargar los ejemplos SAT-Graph: ' + err.message, true);
      }
    }

    function handleUploadedJsonText(rawText) {
      var eng = engine();
      if (!eng) return;
      var parsed;
      try {
        parsed = JSON.parse(rawText);
      } catch (err) {
        showValidation([{ code: 'JSON_PARSE_ERROR', message: err.message }], []);
        return;
      }
      var validation = eng.validateDataset(parsed);
      if (!validation.valid) {
        showValidation(validation.errors, validation.warnings);
        return;
      }
      state.sourceMode = 'upload';
      updateSourceButtons();
      applyDataset(parsed, validation.warnings);
    }

    function bindEvents() {
      refs.srcActiveBtn.addEventListener('click', function () { void loadActiveDocumentDataset(); });
      refs.srcCorpusBtn.addEventListener('click', function () { void loadCorpusDataset(); });
      refs.srcSamplesBtn.addEventListener('click', function () { void loadSamples(); });

      refs.sampleSelect.addEventListener('change', function () {
        var chosen = state.samples.find(function (s) { return s.id === refs.sampleSelect.value; });
        if (chosen && chosen.dataset) applyDataset(chosen.dataset);
      });

      refs.fileInput.addEventListener('change', function () {
        var file = refs.fileInput.files && refs.fileInput.files[0];
        if (!file) return;
        if (typeof file.text === 'function') {
          file.text().then(handleUploadedJsonText, function (err) {
            showValidation([{ code: 'FILE_READ_ERROR', message: err.message }], []);
          });
        } else {
          var reader = new FileReader();
          reader.onload = function () { handleUploadedJsonText(String(reader.result || '')); };
          reader.readAsText(file);
        }
      });

      refs.instantApplyBtn.addEventListener('click', function () {
        setInstant(refs.instantInput.value);
      });
      refs.instantInput.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          setInstant(refs.instantInput.value);
        }
      });

      refs.slider.addEventListener('input', function () {
        syncSliderCustomProperties();
        var idx = Number(refs.slider.value) || 0;
        var tick = state.ticks[idx];
        if (tick) {
          setInstant(tick.iso);
        }
      });

      refs.prevTransBtn.addEventListener('click', function () { stepTransition(-1); });
      refs.nextTransBtn.addEventListener('click', function () { stepTransition(1); });
      refs.minusSBtn.addEventListener('click', function () { stepInstantByMs(-1000); });
      refs.plusSBtn.addEventListener('click', function () { stepInstantByMs(1000); });
      refs.minusMsBtn.addEventListener('click', function () { stepInstantByMs(-1); });
      refs.plusMsBtn.addEventListener('click', function () { stepInstantByMs(1); });

      refs.includeUnknown.addEventListener('change', function () {
        state.includeUnknownSnapshots = Boolean(refs.includeUnknown.checked);
        renderVersionPanels();
        renderRawInspector();
      });

      refs.diffLeftSelect.addEventListener('change', function () {
        state.diffLeftId = refs.diffLeftSelect.value;
        renderDiffPanel();
      });
      refs.diffRightSelect.addEventListener('change', function () {
        state.diffRightId = refs.diffRightSelect.value;
        renderDiffPanel();
      });

      refs.historyItemSelect.addEventListener('change', function () {
        state.selectedItemId = refs.historyItemSelect.value;
        renderRawInspector();
      });

      refs.copyJsonBtn.addEventListener('click', function () {
        var snapshot = state.lastRawSnapshot || {
          at: state.currentInstant,
          validVersions: [],
          itemHistory: [],
        };
        var payload = JSON.stringify(snapshot, null, 2);
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
          navigator.clipboard.writeText(payload).then(function () {
            var b = bridge();
            if (b) b.notify('JSON temporal copiado al portapapeles.');
          }).catch(function () {});
        }
      });
    }

    mountShell();

    var b = bridge();
    if (b) {
      b.onTabActivated('temporal', function (ctx) {
        state.active = true;
        if (!state.dataset || (state.sourceMode === 'active' && ctx.doc && ctx.doc.id !== state.loadedDocId)) {
          if (ctx.doc) void loadActiveDocumentDataset();
          else void loadSamples();
        }
      });
      b.onTabActivated('*', function (_ctx, tab) {
        if (tab !== 'temporal') state.active = false;
      });
      b.onDocumentLoaded(function (ctx) {
        if (state.active && state.sourceMode === 'active' && ctx.doc) {
          void loadActiveDocumentDataset();
        }
      });
    }

    return {
      applyDataset: applyDataset,
      handleUploadedJsonText: handleUploadedJsonText,
      setInstant: setInstant,
      loadSamples: loadSamples,
      loadActiveDocumentDataset: loadActiveDocumentDataset,
      loadCorpusDataset: loadCorpusDataset,
      getState: function () { return state; },
    };
  }

  function init() {
    var controller = createController();
    if (typeof window !== 'undefined' && controller) {
      window.SATTemporalViewer = controller;
    }
  }

  if (document.getElementById('temporal-view')) {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  }
})();
