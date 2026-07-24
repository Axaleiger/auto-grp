/**
 * Загрузка и хранение JSON-экспорта КЛАД для сервисов ЦДП.
 * Приоритет: IndexedDB (загруженный JSON) → window.AUTO_GRP_DATA (auto_grp_data.js).
 */
(function (global) {
  "use strict";

  var DB_NAME = "cdp-platform-data";
  var STORE = "exports";
  var KEY = "current";
  var META_KEY = "cdp_data_meta";

  function openDb() {
    return new Promise(function (resolve, reject) {
      if (!global.indexedDB) {
        reject(new Error("IndexedDB недоступен"));
        return;
      }
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error || new Error("IndexedDB open failed")); };
    });
  }

  function idbPut(value) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(value, KEY);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function idbGet() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly");
        var req = tx.objectStore(STORE).get(KEY);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function idbClear() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(KEY);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  /** Экспорт КЛАД → формат AUTO_GRP_DATA (+ grp_ports, startup) */
  function toAutoGrpData(exportObj) {
    if (!exportObj || typeof exportObj !== "object") throw new Error("Пустой JSON");
    // Уже в формате bundle?
    if (exportObj.layers && !exportObj.schema) {
      return normalizeBundle(exportObj);
    }
    if (exportObj.schema !== "cdp-platform-export" && exportObj.schema !== "cdp-klad-export") {
      // допускаем оба имени + сырой bundle
      if (!exportObj.layers) throw new Error("Неизвестный формат: нет schema/layers");
    }
    var layers = {};
    var grpAll = {};
    var startup = {};
    Object.keys(exportObj.layers || {}).forEach(function (label) {
      var L = exportObj.layers[label] || {};
      layers[label] = {
        maps: L.maps || {},
        trunks: L.trunks || [],
        blocks: L.blocks || {},
        mor: L.mor || [],
        tr: L.tr || []
      };
      var ports = L.grp_ports || {};
      Object.keys(ports).forEach(function (w) { grpAll[w] = ports[w]; });
      if (L.startup) startup[label] = L.startup;
    });
    var bundle = { layers: layers };
    if (exportObj.history) bundle.history = exportObj.history;
    if (Object.keys(grpAll).length) bundle.grp_ports = grpAll;
    if (Object.keys(startup).length) bundle.startup = startup;
    bundle._meta = {
      schema: exportObj.schema || "bundle",
      version: exportObj.version || "",
      exported_at: exportObj.exported_at || "",
      source: exportObj.source || null,
      meta: exportObj.meta || null,
      layers: Object.keys(layers),
      uploaded_at: new Date().toISOString()
    };
    return bundle;
  }

  function normalizeBundle(b) {
    var out = {
      layers: b.layers || {},
      history: b.history,
      grp_ports: b.grp_ports,
      startup: b.startup,
      _meta: b._meta || {
        schema: "AUTO_GRP_DATA",
        layers: Object.keys(b.layers || {}),
        uploaded_at: new Date().toISOString()
      }
    };
    return out;
  }

  function saveMeta(meta) {
    try { localStorage.setItem(META_KEY, JSON.stringify(meta || {})); } catch (e) { /* ignore */ }
  }

  function readMeta() {
    try { return JSON.parse(localStorage.getItem(META_KEY) || "null"); } catch (e) { return null; }
  }

  function saveExport(exportObj) {
    var bundle = toAutoGrpData(exportObj);
    return idbPut(bundle).then(function () {
      saveMeta(bundle._meta);
      global.AUTO_GRP_DATA = bundle;
      if (bundle.grp_ports) global.ROMA_GRP_PORTS = bundle.grp_ports;
      return bundle;
    });
  }

  function clearExport() {
    return idbClear().then(function () {
      try { localStorage.removeItem(META_KEY); } catch (e) { /* ignore */ }
      return true;
    });
  }

  function loadFromUploadFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var text = String(reader.result || "");
          // поддержка .js вида window.AUTO_GRP_DATA={...};
          var jsonText = text;
          var m = text.match(/window\.AUTO_GRP_DATA\s*=\s*([\s\S]*);?\s*$/);
          if (m) jsonText = m[1].replace(/;+\s*$/, "");
          var obj = JSON.parse(jsonText);
          saveExport(obj).then(resolve).catch(reject);
        } catch (err) {
          reject(err);
        }
      };
      reader.onerror = function () { reject(reader.error || new Error("Не удалось прочитать файл")); };
      reader.readAsText(file);
    });
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error("Не загружен " + src)); };
      document.head.appendChild(s);
    });
  }

  /**
   * Основная точка входа для сервисов.
   * Возвращает Promise<AUTO_GRP_DATA-like>.
   */
  function loadPlatformData(opts) {
    opts = opts || {};
    return idbGet().then(function (stored) {
      if (stored && stored.layers && Object.keys(stored.layers).length) {
        global.AUTO_GRP_DATA = stored;
        if (stored.grp_ports) global.ROMA_GRP_PORTS = stored.grp_ports;
        return stored;
      }
      if (global.AUTO_GRP_DATA && global.AUTO_GRP_DATA.layers) {
        return normalizeBundle(global.AUTO_GRP_DATA);
      }
      if (opts.fallbackScript === false) {
        throw new Error("Нет загруженного JSON. Откройте каталог → Данные.");
      }
      var script = opts.fallbackScript || "auto_grp_data.js";
      return loadScript(script).then(function () {
        if (!global.AUTO_GRP_DATA) throw new Error("AUTO_GRP_DATA пуст после " + script);
        return normalizeBundle(global.AUTO_GRP_DATA);
      });
    });
  }

  function statusSummary() {
    var meta = readMeta();
    return idbGet().then(function (stored) {
      if (stored && stored.layers) {
        var labels = Object.keys(stored.layers);
        return {
          source: "klad-json",
          layers: labels,
          exported_at: (stored._meta && stored._meta.exported_at) || (meta && meta.exported_at) || "",
          uploaded_at: (stored._meta && stored._meta.uploaded_at) || (meta && meta.uploaded_at) || "",
          field: (stored._meta && stored._meta.meta && stored._meta.meta.field) || (meta && meta.meta && meta.meta.field) || ""
        };
      }
      return { source: "builtin", layers: [], exported_at: "", uploaded_at: "", field: "" };
    }).catch(function () {
      return { source: "none", layers: [], exported_at: "", uploaded_at: "", field: "" };
    });
  }

  global.CdpPlatformData = {
    toAutoGrpData: toAutoGrpData,
    saveExport: saveExport,
    clearExport: clearExport,
    loadFromUploadFile: loadFromUploadFile,
    loadPlatformData: loadPlatformData,
    statusSummary: statusSummary,
    readMeta: readMeta
  };
})(typeof window !== "undefined" ? window : globalThis);
