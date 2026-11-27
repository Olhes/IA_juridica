(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && typeof module.exports === 'object') {
    module.exports = api;
  }
  if (root && typeof root === 'object') {
    root.SATTemporalEngine = api;
  }
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  var DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
  var RFC3339_RE = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|z|([+-])(\d{2}):(\d{2}))$/;

  function isLeapYear(year) {
    return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  }

  function daysInMonth(year, month) {
    if (month === 2) {
      return isLeapYear(year) ? 29 : 28;
    }
    if (month === 4 || month === 6 || month === 9 || month === 11) {
      return 30;
    }
    return 31;
  }

  function validateCalendarDate(year, month, day, raw) {
    if (month < 1 || month > 12) {
      throw new TypeError('Invalid calendar month in instant: ' + raw);
    }
    var maxDay = daysInMonth(year, month);
    if (day < 1 || day > maxDay) {
      throw new TypeError('Invalid calendar date in instant: ' + raw);
    }
  }

  function parseQueryInstant(value) {
    if (typeof value !== 'string') {
      throw new TypeError('Temporal instant must be a string in YYYY-MM-DD or RFC 3339 format');
    }
    var raw = value.trim();
    if (!raw || raw !== value) {
      throw new TypeError('Temporal instant must not be empty or padded with whitespace');
    }

    var dateMatch = DATE_ONLY_RE.exec(raw);
    if (dateMatch) {
      var y = parseInt(dateMatch[1], 10);
      var m = parseInt(dateMatch[2], 10);
      var d = parseInt(dateMatch[3], 10);
      validateCalendarDate(y, m, d, raw);
      return new Date(Date.UTC(y, m - 1, d, 0, 0, 0, 0));
    }

    var tsMatch = RFC3339_RE.exec(raw);
    if (!tsMatch) {
      throw new TypeError('Temporal instant must be YYYY-MM-DD or strict RFC 3339 with explicit offset: ' + raw);
    }

    var year = parseInt(tsMatch[1], 10);
    var month = parseInt(tsMatch[2], 10);
    var day = parseInt(tsMatch[3], 10);
    var hour = parseInt(tsMatch[4], 10);
    var minute = parseInt(tsMatch[5], 10);
    var second = parseInt(tsMatch[6], 10);
    var frac = tsMatch[7] || '';
    var tzToken = tsMatch[8];

    validateCalendarDate(year, month, day, raw);
    if (hour > 23 || minute > 59 || second > 59) {
      throw new TypeError('Invalid clock time in instant: ' + raw);
    }

    var ms = frac ? parseInt((frac + '000').slice(0, 3), 10) : 0;
    var offsetMinutes = 0;
    if (tzToken !== 'Z' && tzToken !== 'z') {
      var sign = tsMatch[9] === '-' ? -1 : 1;
      var offHours = parseInt(tsMatch[10], 10);
      var offMins = parseInt(tsMatch[11], 10);
      if (offHours > 23 || offMins > 59) {
        throw new TypeError('Invalid timezone offset in instant: ' + raw);
      }
      offsetMinutes = sign * (offHours * 60 + offMins);
    }

    var utcMs = Date.UTC(year, month - 1, day, hour, minute, second, ms) - offsetMinutes * 60000;
    return new Date(utcMs);
  }

  function parseInstantMs(value) {
    return parseQueryInstant(value).getTime();
  }

  function normalizeInstantISO(value) {
    var date = parseQueryInstant(value);
    var iso = date.toISOString();
    return date.getUTCMilliseconds() === 0 ? iso.replace('.000Z', 'Z') : iso;
  }

  function coerceInstantMs(at) {
    if (at instanceof Date) {
      var t = at.getTime();
      if (!Number.isFinite(t)) {
        throw new TypeError('Invalid Date instance');
      }
      return t;
    }
    if (typeof at === 'number') {
      if (!Number.isFinite(at)) {
        throw new TypeError('Instant epoch milliseconds must be finite');
      }
      return at;
    }
    return parseInstantMs(at);
  }

  function cloneMeta(meta) {
    if (!meta || typeof meta !== 'object' || Array.isArray(meta)) {
      return {};
    }
    return Object.assign({}, meta);
  }

  function extractInterval(version) {
    if (Array.isArray(version.validityInterval)) {
      return [
        version.validityInterval[0] === undefined ? null : version.validityInterval[0],
        version.validityInterval[1] === undefined ? null : version.validityInterval[1],
      ];
    }
    if (version.validity && typeof version.validity === 'object' && !Array.isArray(version.validity)) {
      var startObj = version.validity.start !== undefined ? version.validity.start : version.validity.from;
      var endObj = version.validity.end !== undefined ? version.validity.end : version.validity.to;
      return [
        startObj === undefined ? null : startObj,
        endObj === undefined ? null : endObj,
      ];
    }
    if (
      'validFrom' in version ||
      'validTo' in version ||
      'valid_from' in version ||
      'valid_to' in version
    ) {
      var startField = version.validFrom !== undefined ? version.validFrom : version.valid_from;
      var endField = version.validTo !== undefined ? version.validTo : version.valid_to;
      return [
        startField === undefined ? null : startField,
        endField === undefined ? null : endField,
      ];
    }
    return [null, null];
  }

  function normalizeDataset(raw) {
    var src = raw && typeof raw === 'object' ? raw : {};
    var rawItems = Array.isArray(src.items) ? src.items : [];
    var rawVersions = Array.isArray(src.versions) ? src.versions : [];
    var rawActions = Array.isArray(src.actions) ? src.actions : [];
    var rawTextUnits = Array.isArray(src.textUnits)
      ? src.textUnits
      : (Array.isArray(src.text_units) ? src.text_units : []);

    var items = rawItems.map(function (item) {
      var entry = item && typeof item === 'object' ? item : {};
      return {
        id: entry.id,
        typeId: entry.typeId !== undefined ? entry.typeId : (entry.type || 'item'),
        label: entry.label !== undefined ? entry.label : (entry.title || entry.name || String(entry.id || '')),
        parentId: entry.parentId !== undefined ? entry.parentId : (entry.parent_id !== undefined ? entry.parent_id : null),
        url: entry.url !== undefined ? entry.url : null,
        metadata: cloneMeta(entry.metadata),
      };
    });

    var textUnits = rawTextUnits.map(function (unit) {
      var entry = unit && typeof unit === 'object' ? unit : {};
      var sourceId = entry.sourceId !== undefined
        ? entry.sourceId
        : (entry.versionId !== undefined ? entry.versionId : entry.version_id);
      return {
        id: entry.id,
        sourceType: entry.sourceType || 'Version',
        sourceId: sourceId,
        language: entry.language || 'es',
        aspect: entry.aspect || 'canonical',
        content: entry.content !== undefined ? entry.content : (entry.text !== undefined ? entry.text : ''),
        metadata: cloneMeta(entry.metadata),
      };
    });

    var versionsWithText = Object.create(null);
    for (var ti = 0; ti < textUnits.length; ti++) {
      if (textUnits[ti].sourceId) {
        versionsWithText[textUnits[ti].sourceId] = true;
      }
    }

    var versions = rawVersions.map(function (version) {
      var entry = version && typeof version === 'object' ? version : {};
      var interval = extractInterval(entry);
      var meta = cloneMeta(entry.metadata);
      if (interval[0] === null && interval[1] === null && meta.legalIntervalKnown === undefined) {
        meta.legalIntervalKnown = false;
      }
      var itemId = entry.itemId !== undefined
        ? entry.itemId
        : (entry.item_id !== undefined ? entry.item_id : (entry.workId !== undefined ? entry.workId : entry.work_id));
      var normalizedVersion = {
        id: entry.id,
        itemId: itemId,
        type: entry.type || entry.versionType || 'statutory',
        validityInterval: interval,
        metadata: meta,
      };

      var inlineText = entry.content !== undefined ? entry.content : entry.text;
      if (typeof inlineText === 'string' && entry.id && !versionsWithText[entry.id]) {
        versionsWithText[entry.id] = true;
        textUnits.push({
          id: 'tu:' + entry.id,
          sourceType: 'Version',
          sourceId: entry.id,
          language: entry.language || meta.language || 'es',
          aspect: entry.aspect || 'canonical',
          content: inlineText,
          metadata: { liftedFromVersion: true },
        });
      }
      return normalizedVersion;
    });

    var actions = rawActions.map(function (action) {
      var entry = action && typeof action === 'object' ? action : {};
      var kind = entry.kind !== undefined ? entry.kind : (entry.type || 'action');
      var eventTime = entry.eventTime !== undefined
        ? entry.eventTime
        : (entry.effectiveTime !== undefined
          ? entry.effectiveTime
          : (entry.effective_time !== undefined
            ? entry.effective_time
            : (entry.effectiveOn !== undefined ? entry.effectiveOn : (entry.effective_on !== undefined ? entry.effective_on : null))));
      var terminatesRaw = entry.terminatesVersionIds !== undefined
        ? entry.terminatesVersionIds
        : (entry.terminates !== undefined ? entry.terminates : entry.supersedes);
      var producesRaw = entry.producesVersionIds !== undefined
        ? entry.producesVersionIds
        : entry.produces;
      var meta = cloneMeta(entry.metadata);
      if (Array.isArray(entry.itemIds) && !meta.itemIds) {
        meta.itemIds = entry.itemIds.slice();
      } else if (typeof entry.itemId === 'string' && !meta.itemIds) {
        meta.itemIds = [entry.itemId];
      }
      return {
        id: entry.id,
        kind: kind,
        eventTime: eventTime === undefined ? null : eventTime,
        terminatesVersionIds: Array.isArray(terminatesRaw) ? terminatesRaw.slice() : [],
        producesVersionIds: Array.isArray(producesRaw) ? producesRaw.slice() : [],
        sourceId: entry.sourceId !== undefined ? entry.sourceId : (entry.source_id !== undefined ? entry.source_id : null),
        label: entry.label !== undefined ? entry.label : (entry.title !== undefined ? entry.title : String(kind || entry.id || '')),
        metadata: meta,
      };
    });

    return {
      schemaVersion: src.schemaVersion || 'sat-graph-viewer/1',
      source: src.source || 'uploaded-json',
      resourceId: src.resourceId !== undefined ? src.resourceId : null,
      title: src.title || '',
      policyNote: src.policyNote || '',
      items: items,
      versions: versions,
      actions: actions,
      textUnits: textUnits,
      metadata: cloneMeta(src.metadata),
    };
  }

  function isInHalfOpenInterval(instantMs, interval, options) {
    var queryMs = coerceInstantMs(instantMs);
    var start = null;
    var end = null;
    if (Array.isArray(interval)) {
      start = interval[0] === undefined ? null : interval[0];
      end = interval[1] === undefined ? null : interval[1];
    } else if (interval && typeof interval === 'object') {
      start = interval.start !== undefined ? interval.start : (interval.from !== undefined ? interval.from : null);
      end = interval.end !== undefined ? interval.end : (interval.to !== undefined ? interval.to : null);
    }

    if (start === null && end === null) {
      return Boolean(options && options.includeUnknownSnapshots);
    }

    var startMs = start === null ? null : coerceInstantMs(start);
    var endMs = end === null ? null : coerceInstantMs(end);

    if (startMs !== null && endMs !== null && endMs <= startMs) {
      return false;
    }
    if (startMs !== null && queryMs < startMs) {
      return false;
    }
    if (endMs !== null && queryMs >= endMs) {
      return false;
    }
    return true;
  }

  function getValidVersions(dataset, at, options) {
    var norm = normalizeDataset(dataset);
    var atMs = coerceInstantMs(at);
    var opts = options && typeof options === 'object' ? options : {};
    var includeUnknown = Boolean(opts.includeUnknownSnapshots);
    var filterItemId = opts.itemId !== undefined && opts.itemId !== null ? opts.itemId : null;
    var filterType = opts.type !== undefined && opts.type !== null ? opts.type : null;

    var seen = Object.create(null);
    var result = [];
    for (var i = 0; i < norm.versions.length; i++) {
      var version = norm.versions[i];
      if (!version.id || seen[version.id]) {
        continue;
      }
      if (filterItemId !== null && version.itemId !== filterItemId) {
        continue;
      }
      if (filterType !== null && version.type !== filterType) {
        continue;
      }
      if (isInHalfOpenInterval(atMs, version.validityInterval, { includeUnknownSnapshots: includeUnknown })) {
        seen[version.id] = true;
        result.push(version);
      }
    }
    return result;
  }

  function compareIds(a, b) {
    var sa = String(a || '');
    var sb = String(b || '');
    return sa < sb ? -1 : (sa > sb ? 1 : 0);
  }

  function tryParseInstantMs(value) {
    if (value === null || value === undefined) {
      return null;
    }
    try {
      return parseInstantMs(value);
    } catch (_err) {
      return null;
    }
  }

  function getItemHistory(dataset, itemId) {
    var norm = normalizeDataset(dataset);
    var versionIds = Object.create(null);
    for (var i = 0; i < norm.versions.length; i++) {
      if (norm.versions[i].itemId === itemId) {
        versionIds[norm.versions[i].id] = true;
      }
    }

    var matched = [];
    for (var j = 0; j < norm.actions.length; j++) {
      var action = norm.actions[j];
      var touches = false;
      for (var t = 0; t < action.terminatesVersionIds.length; t++) {
        if (versionIds[action.terminatesVersionIds[t]]) {
          touches = true;
          break;
        }
      }
      if (!touches) {
        for (var p = 0; p < action.producesVersionIds.length; p++) {
          if (versionIds[action.producesVersionIds[p]]) {
            touches = true;
            break;
          }
        }
      }
      if (!touches && Array.isArray(action.metadata.itemIds) && action.metadata.itemIds.indexOf(itemId) !== -1) {
        touches = true;
      }
      if (touches) {
        matched.push({
          action: action,
          ms: tryParseInstantMs(action.eventTime),
        });
      }
    }

    matched.sort(function (left, right) {
      if (left.ms === null && right.ms === null) {
        return compareIds(left.action.id, right.action.id);
      }
      if (left.ms === null) {
        return 1;
      }
      if (right.ms === null) {
        return -1;
      }
      if (left.ms !== right.ms) {
        return left.ms - right.ms;
      }
      return compareIds(left.action.id, right.action.id);
    });

    return matched.map(function (entry) {
      return entry.action;
    });
  }

  function validateDataset(raw) {
    var errors = [];
    var warnings = [];

    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      return {
        valid: false,
        errors: [{ code: 'INVALID_ROOT', message: 'Dataset must be a JSON object' }],
        warnings: [],
        stats: { items: 0, versions: 0, actions: 0, textUnits: 0 },
      };
    }

    if (!Array.isArray(raw.items)) {
      errors.push({ code: 'MISSING_ITEMS', message: 'Dataset must contain an "items" array' });
    }
    if (!Array.isArray(raw.versions)) {
      errors.push({ code: 'MISSING_VERSIONS', message: 'Dataset must contain a "versions" array' });
    }
    if (raw.actions !== undefined && !Array.isArray(raw.actions)) {
      errors.push({ code: 'INVALID_ACTIONS', message: '"actions" must be an array when provided' });
    }
    if (raw.textUnits !== undefined && !Array.isArray(raw.textUnits)) {
      errors.push({ code: 'INVALID_TEXT_UNITS', message: '"textUnits" must be an array when provided' });
    }

    var norm = normalizeDataset(raw);
    var itemById = Object.create(null);
    for (var i = 0; i < norm.items.length; i++) {
      var item = norm.items[i];
      if (!item.id || typeof item.id !== 'string') {
        errors.push({ code: 'MISSING_ITEM_ID', message: 'Every item requires a non-empty string id' });
        continue;
      }
      if (itemById[item.id]) {
        errors.push({ code: 'DUPLICATE_ITEM_ID', message: 'Duplicate item id: ' + item.id, entityId: item.id });
      }
      itemById[item.id] = item;
    }

    for (var pi = 0; pi < norm.items.length; pi++) {
      var parentRef = norm.items[pi].parentId;
      if (parentRef !== null && parentRef !== undefined && !itemById[parentRef]) {
        errors.push({
          code: 'BROKEN_ITEM_PARENT',
          message: 'Item "' + norm.items[pi].id + '" references missing parentId "' + parentRef + '"',
          entityId: norm.items[pi].id,
        });
      }
    }

    var versionById = Object.create(null);
    var parsedIntervals = Object.create(null);
    var statutoryByItem = Object.create(null);

    for (var vi = 0; vi < norm.versions.length; vi++) {
      var v = norm.versions[vi];
      if (!v.id || typeof v.id !== 'string') {
        errors.push({ code: 'MISSING_VERSION_ID', message: 'Every version requires a non-empty string id' });
        continue;
      }
      if (versionById[v.id]) {
        errors.push({ code: 'DUPLICATE_VERSION_ID', message: 'Duplicate version id: ' + v.id, entityId: v.id });
      }
      versionById[v.id] = v;

      if (!v.itemId || !itemById[v.itemId]) {
        errors.push({
          code: 'BROKEN_VERSION_ITEM',
          message: 'Version "' + v.id + '" references missing itemId "' + v.itemId + '"',
          entityId: v.id,
        });
      }

      var start = v.validityInterval[0];
      var end = v.validityInterval[1];
      if (start === null && end === null) {
        warnings.push({
          code: 'UNKNOWN_LEGAL_INTERVAL',
          message: 'Version "' + v.id + '" has [null, null] unknown legal validity interval',
          entityId: v.id,
        });
        parsedIntervals[v.id] = { startMs: null, endMs: null };
      } else {
        var startMs = null;
        var endMs = null;
        var validBounds = true;
        if (start !== null) {
          try {
            startMs = parseInstantMs(start);
          } catch (errStart) {
            validBounds = false;
            errors.push({
              code: 'INVALID_VERSION_INSTANT',
              message: 'Version "' + v.id + '" has invalid start instant: ' + errStart.message,
              entityId: v.id,
            });
          }
        }
        if (end !== null) {
          try {
            endMs = parseInstantMs(end);
          } catch (errEnd) {
            validBounds = false;
            errors.push({
              code: 'INVALID_VERSION_INSTANT',
              message: 'Version "' + v.id + '" has invalid end instant: ' + errEnd.message,
              entityId: v.id,
            });
          }
        }
        if (validBounds && startMs !== null && endMs !== null && endMs <= startMs) {
          errors.push({
            code: 'INVERTED_INTERVAL',
            message: 'Version "' + v.id + '" has end <= start in half-open interval',
            entityId: v.id,
          });
        }
        if (validBounds) {
          parsedIntervals[v.id] = { startMs: startMs, endMs: endMs };
          if (v.type === 'statutory' && !v.metadata.archived && startMs !== null) {
            if (!statutoryByItem[v.itemId]) {
              statutoryByItem[v.itemId] = [];
            }
            statutoryByItem[v.itemId].push({ version: v, startMs: startMs, endMs: endMs });
          }
        }
      }
    }

    var itemKeys = Object.keys(statutoryByItem);
    for (var k = 0; k < itemKeys.length; k++) {
      var list = statutoryByItem[itemKeys[k]];
      list.sort(function (a, b) {
        if (a.startMs !== b.startMs) {
          return a.startMs - b.startMs;
        }
        return compareIds(a.version.id, b.version.id);
      });
      for (var s = 0; s < list.length - 1; s++) {
        var left = list[s];
        var right = list[s + 1];
        if (left.endMs === null || left.endMs > right.startMs) {
          errors.push({
            code: 'STATUTORY_OVERLAP',
            message: 'Statutory versions "' + left.version.id + '" and "' + right.version.id + '" overlap on item "' + itemKeys[k] + '"',
            entityId: right.version.id,
          });
        }
      }
    }

    var actionIds = Object.create(null);
    for (var ai = 0; ai < norm.actions.length; ai++) {
      var act = norm.actions[ai];
      if (!act.id || typeof act.id !== 'string') {
        errors.push({ code: 'MISSING_ACTION_ID', message: 'Every action requires a non-empty string id' });
        continue;
      }
      if (actionIds[act.id]) {
        errors.push({ code: 'DUPLICATE_ACTION_ID', message: 'Duplicate action id: ' + act.id, entityId: act.id });
      }
      actionIds[act.id] = true;

      if (act.eventTime !== null) {
        try {
          parseInstantMs(act.eventTime);
        } catch (errAct) {
          errors.push({
            code: 'INVALID_ACTION_INSTANT',
            message: 'Action "' + act.id + '" has invalid eventTime: ' + errAct.message,
            entityId: act.id,
          });
        }
      }

      for (var ti2 = 0; ti2 < act.terminatesVersionIds.length; ti2++) {
        var termId = act.terminatesVersionIds[ti2];
        if (!versionById[termId]) {
          errors.push({
            code: 'BROKEN_ACTION_VERSION',
            message: 'Action "' + act.id + '" terminates missing version "' + termId + '"',
            entityId: act.id,
          });
        }
      }
      for (var pi2 = 0; pi2 < act.producesVersionIds.length; pi2++) {
        var prodId = act.producesVersionIds[pi2];
        if (!versionById[prodId]) {
          errors.push({
            code: 'BROKEN_ACTION_VERSION',
            message: 'Action "' + act.id + '" produces missing version "' + prodId + '"',
            entityId: act.id,
          });
        }
      }

      if (act.kind !== 'editorial_revision') {
        for (var tx = 0; tx < act.terminatesVersionIds.length; tx++) {
          var tVer = versionById[act.terminatesVersionIds[tx]];
          var tIv = tVer ? parsedIntervals[tVer.id] : null;
          if (!tVer || tVer.type !== 'statutory' || !tIv || tIv.startMs === null) {
            continue;
          }
          for (var px = 0; px < act.producesVersionIds.length; px++) {
            var pVer = versionById[act.producesVersionIds[px]];
            var pIv = pVer ? parsedIntervals[pVer.id] : null;
            if (!pVer || pVer.type !== 'statutory' || pVer.itemId !== tVer.itemId || !pIv || pIv.startMs === null) {
              continue;
            }
            if (tIv.endMs === null || tIv.endMs > pIv.startMs) {
              errors.push({
                code: 'SUPERSESSION_OVERLAP',
                message: 'Action "' + act.id + '" supersedes "' + tVer.id + '" with "' + pVer.id + '" but their statutory intervals overlap',
                entityId: act.id,
              });
            }
          }
        }
      }
    }

    var textUnitIds = Object.create(null);
    for (var ui = 0; ui < norm.textUnits.length; ui++) {
      var unit = norm.textUnits[ui];
      if (!unit.id || typeof unit.id !== 'string') {
        errors.push({ code: 'MISSING_TEXT_UNIT_ID', message: 'Every textUnit requires a non-empty string id' });
        continue;
      }
      if (textUnitIds[unit.id]) {
        errors.push({ code: 'DUPLICATE_TEXT_UNIT_ID', message: 'Duplicate textUnit id: ' + unit.id, entityId: unit.id });
      }
      textUnitIds[unit.id] = true;
      if (!unit.sourceId || !versionById[unit.sourceId]) {
        errors.push({
          code: 'BROKEN_TEXT_UNIT_SOURCE',
          message: 'TextUnit "' + unit.id + '" references missing version "' + unit.sourceId + '"',
          entityId: unit.id,
        });
      }
    }

    return {
      valid: errors.length === 0,
      errors: errors,
      warnings: warnings,
      stats: {
        items: norm.items.length,
        versions: norm.versions.length,
        actions: norm.actions.length,
        textUnits: norm.textUnits.length,
      },
    };
  }

  function collectTimelineTicks(dataset) {
    var norm = normalizeDataset(dataset);
    var byMs = Object.create(null);

    function record(rawInstant, kind, label) {
      if (rawInstant === null || rawInstant === undefined) {
        return;
      }
      var ms;
      var iso;
      try {
        ms = parseInstantMs(rawInstant);
        iso = normalizeInstantISO(rawInstant);
      } catch (_err) {
        return;
      }
      var key = String(ms);
      if (!byMs[key]) {
        byMs[key] = { iso: iso, ms: ms, label: label || iso, kinds: [] };
      }
      if (byMs[key].kinds.indexOf(kind) === -1) {
        byMs[key].kinds.push(kind);
      }
      if (label && byMs[key].label === iso) {
        byMs[key].label = label;
      }
    }

    for (var i = 0; i < norm.versions.length; i++) {
      var v = norm.versions[i];
      var iv = v.validityInterval;
      if (iv[0] !== null) {
        record(iv[0], 'version_start', 'Inicio: ' + v.id);
      }
      if (iv[1] !== null) {
        record(iv[1], 'version_end', 'Fin: ' + v.id);
      }
      if (iv[0] === null && iv[1] === null && v.metadata && v.metadata.snapshotAsOf) {
        record(v.metadata.snapshotAsOf, 'snapshot_as_of', 'Captura: ' + v.id);
      }
    }

    for (var j = 0; j < norm.actions.length; j++) {
      var act = norm.actions[j];
      if (act.eventTime !== null) {
        record(act.eventTime, act.kind, act.label || act.id);
      }
    }

    return Object.keys(byMs)
      .map(function (key) {
        return byMs[key];
      })
      .sort(function (a, b) {
        return a.ms - b.ms;
      });
  }

  function mergeDiffOps(ops) {
    var merged = [];
    for (var i = 0; i < ops.length; i++) {
      var cur = ops[i];
      if (!cur.text) {
        continue;
      }
      if (merged.length > 0 && merged[merged.length - 1].op === cur.op) {
        merged[merged.length - 1].text += cur.text;
      } else {
        merged.push({ op: cur.op, text: cur.text });
      }
    }
    return merged;
  }

  function lcsDiffTokens(aTokens, bTokens) {
    var prefix = 0;
    while (prefix < aTokens.length && prefix < bTokens.length && aTokens[prefix] === bTokens[prefix]) {
      prefix++;
    }
    var suffix = 0;
    while (
      suffix < aTokens.length - prefix &&
      suffix < bTokens.length - prefix &&
      aTokens[aTokens.length - 1 - suffix] === bTokens[bTokens.length - 1 - suffix]
    ) {
      suffix++;
    }

    var aMid = aTokens.slice(prefix, aTokens.length - suffix);
    var bMid = bTokens.slice(prefix, bTokens.length - suffix);
    var ops = [];

    if (prefix > 0) {
      ops.push({ op: 'equal', text: aTokens.slice(0, prefix).join('') });
    }

    var m = aMid.length;
    var n = bMid.length;
    if (m === 0 && n > 0) {
      ops.push({ op: 'insert', text: bMid.join('') });
    } else if (n === 0 && m > 0) {
      ops.push({ op: 'delete', text: aMid.join('') });
    } else if (m > 0 && n > 0 && m * n > 4000000) {
      ops.push({ op: 'delete', text: aMid.join('') });
      ops.push({ op: 'insert', text: bMid.join('') });
    } else if (m > 0 && n > 0) {
      var width = n + 1;
      var dp = new Int32Array((m + 1) * width);
      for (var i = m - 1; i >= 0; i--) {
        var rowOffset = i * width;
        var nextRowOffset = (i + 1) * width;
        for (var j = n - 1; j >= 0; j--) {
          if (aMid[i] === bMid[j]) {
            dp[rowOffset + j] = dp[nextRowOffset + j + 1] + 1;
          } else {
            var down = dp[nextRowOffset + j];
            var right = dp[rowOffset + j + 1];
            dp[rowOffset + j] = down >= right ? down : right;
          }
        }
      }

      var ai = 0;
      var bi = 0;
      while (ai < m && bi < n) {
        if (aMid[ai] === bMid[bi]) {
          ops.push({ op: 'equal', text: aMid[ai] });
          ai++;
          bi++;
        } else if (dp[(ai + 1) * width + bi] >= dp[ai * width + (bi + 1)]) {
          ops.push({ op: 'delete', text: aMid[ai] });
          ai++;
        } else {
          ops.push({ op: 'insert', text: bMid[bi] });
          bi++;
        }
      }
      while (ai < m) {
        ops.push({ op: 'delete', text: aMid[ai] });
        ai++;
      }
      while (bi < n) {
        ops.push({ op: 'insert', text: bMid[bi] });
        bi++;
      }
    }

    if (suffix > 0) {
      ops.push({ op: 'equal', text: aTokens.slice(aTokens.length - suffix).join('') });
    }

    return mergeDiffOps(ops);
  }

  function diffVersionTexts(beforeText, afterText) {
    var left = typeof beforeText === 'string' ? beforeText : '';
    var right = typeof afterText === 'string' ? afterText : '';
    if (left === right) {
      return left ? [{ op: 'equal', text: left }] : [];
    }
    if (!left) {
      return [{ op: 'insert', text: right }];
    }
    if (!right) {
      return [{ op: 'delete', text: left }];
    }

    var leftWords = left.match(/\S+|[ \t]+|\r?\n/g) || [left];
    var rightWords = right.match(/\S+|[ \t]+|\r?\n/g) || [right];
    if (leftWords.length * rightWords.length <= 2500000) {
      return lcsDiffTokens(leftWords, rightWords);
    }

    var leftLines = left.match(/[^\r\n]*\r?\n|[^\r\n]+/g) || [left];
    var rightLines = right.match(/[^\r\n]*\r?\n|[^\r\n]+/g) || [right];
    return lcsDiffTokens(leftLines, rightLines);
  }

  return {
    parseQueryInstant: parseQueryInstant,
    parseInstantMs: parseInstantMs,
    normalizeInstantISO: normalizeInstantISO,
    normalizeDataset: normalizeDataset,
    isInHalfOpenInterval: isInHalfOpenInterval,
    getValidVersions: getValidVersions,
    getItemHistory: getItemHistory,
    validateDataset: validateDataset,
    collectTimelineTicks: collectTimelineTicks,
    diffVersionTexts: diffVersionTexts,
  };
});
