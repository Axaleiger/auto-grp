#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для IDE / Jupyter: собрать JSON-пакет данных ЦДП.

Как пользоваться:
  1. Вставьте этот файл в IDE (или откройте целиком в Jupyter)
  2. Заполните блок CONFIG ниже (URL, токен, layer_id, период)
  3. Запустите файл / ячейку
  4. Рядом появится cdp_export.json — подключите его в платформе → «Данные»

Нужен только стандартный Python 3 (+ urllib). Внешние пакеты не обязательны.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# =============================================================================
# CONFIG — заполните и запустите
# =============================================================================

CONFIG = {
    # Базовый URL API (без слэша в конце)
    "base_url": "https://data.example.corp/api",

    # Токен: либо строка здесь, либо имя переменной окружения
    "token": "",                      # например "eyJ..."
    "token_env": "CDP_DATA_TOKEN",    # если token пустой — берётся из env

    "timeout_sec": 120,

    # Метаданные пакета
    "do": "Хантос",
    "field": "Романовское",
    "field_id": "REPLACE_FIELD_ID",
    "exported_by": "",

    # Период
    "date_from": "2024-01-01",
    "date_to": "2026-06-01",

    # Какие блоки данных тянуть
    "datasets": [
        "trunks",      # стволы / координаты
        "blocks",      # контуры блоков
        "mor",         # МЭР
        "tr",          # техрежим Pзаб
        "maps",        # карты Pпл
        "grp_ports",   # порты МГРП
        "history",     # история добычи (по field_id)
        "startup",     # дефолты запускных
    ],

    # Пласты: label в пакете + layer_id в API
    "layers": [
        {"label": "2БС10", "layer_id": "REPLACE_LAYER_ID_2BS10"},
        {"label": "БС9/1", "layer_id": "REPLACE_LAYER_ID_BS9_1"},
    ],

    # Куда сохранить результат (относительно текущей папки или абсолютный путь)
    "output_json": "cdp_export.json",
}

# Эндпоинты относительно base_url. Подставьте реальные пути вашей системы.
ENDPOINTS = {
    "trunks":    "/layers/{layer_id}/wells",
    "blocks":    "/layers/{layer_id}/blocks",
    "mor":       "/layers/{layer_id}/mer",
    "tr":        "/layers/{layer_id}/tr",
    "maps":      "/layers/{layer_id}/pressure-maps",
    "grp_ports": "/layers/{layer_id}/frac-ports",
    "history":   "/fields/{field_id}/production-history",
    "startup":   "/layers/{layer_id}/startup-params",
}

# =============================================================================
# HTTP
# =============================================================================

def _token() -> str:
    t = (CONFIG.get("token") or "").strip()
    if t:
        return t
    env = CONFIG.get("token_env") or "CDP_DATA_TOKEN"
    t = (os.environ.get(env) or "").strip()
    if not t:
        raise SystemExit(
            f"Задайте CONFIG['token'] или переменную окружения {env}"
        )
    return t


def api_get(path: str, params: Optional[dict] = None) -> Any:
    base = CONFIG["base_url"].rstrip("/")
    url = base + path
    if params:
        url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/json",
            "User-Agent": "cdp-pull-data/1.0",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=int(CONFIG.get("timeout_sec") or 120), context=ctx) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code} {url}\n{body}") from e
    except URLError as e:
        raise SystemExit(f"Сеть: {e.reason}\nURL: {url}") from e
    return json.loads(raw) if raw.strip() else None


def _as_list(data: Any) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "rows", "data", "wells", "result"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _as_dict(data: Any, *keys: str) -> dict:
    if data is None:
        return {}
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), dict):
                return data[key]
        # уже словарь сущностей
        if not any(k in data for k in ("items", "rows", "data")):
            return data
    return {}


# =============================================================================
# Нормализация ответов API → формат пакета платформы
# При необходимости поправьте маппинг полей под ваш API.
# =============================================================================

def norm_trunks(rows: list) -> list:
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        w = str(r.get("w") or r.get("well") or r.get("well_name") or r.get("name") or "").strip()
        if not w:
            continue
        item = {
            "w": w,
            "x": float(r.get("x") or r.get("x1") or r.get("t1_x") or 0),
            "y": float(r.get("y") or r.get("y1") or r.get("t1_y") or 0),
        }
        x3 = r.get("x3") or r.get("t3_x")
        y3 = r.get("y3") or r.get("t3_y")
        if x3 not in (None, "") and y3 not in (None, ""):
            item["x3"] = float(x3)
            item["y3"] = float(y3)
            item["hz"] = True
        elif r.get("hz"):
            item["hz"] = True
        out.append(item)
    return out


def norm_blocks(data: Any) -> dict:
    if isinstance(data, dict) and "blocks" in data:
        data = data["blocks"]
    if isinstance(data, list):
        blocks: Dict[str, list] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            bid = str(row.get("block_id") or row.get("name") or row.get("id") or "").strip()
            pts = row.get("points") or row.get("coords") or []
            if bid and isinstance(pts, list):
                blocks[bid] = [[float(p[0]), float(p[1])] for p in pts if len(p) >= 2]
        return blocks
    if isinstance(data, dict):
        out = {}
        for bid, pts in data.items():
            if isinstance(pts, list):
                out[str(bid)] = [[float(p[0]), float(p[1])] for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
        return out
    return {}


def norm_mor(rows: list) -> list:
    out = []
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 5:
            out.append([str(r[0]), str(r[1]), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0)])
            continue
        if not isinstance(r, dict):
            continue
        well = str(r.get("well") or r.get("w") or r.get("well_name") or "").strip()
        date = str(r.get("date") or r.get("dt") or "").strip()
        inj = float(r.get("inj") or r.get("injection") or r.get("zakachka") or 0)
        liq = float(r.get("liq") or r.get("liquid") or r.get("fluid") or 0)
        oil = float(r.get("oil") or r.get("oil_prod") or 0)
        if well and date:
            out.append([well, date, round(inj, 1), round(liq, 1), round(oil, 1)])
    return out


def norm_tr(rows: list) -> list:
    out = []
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 3:
            qliq = float(r[3]) if len(r) > 3 else 0.0
            out.append([str(r[0]), str(r[1]), float(r[2]), round(qliq, 2)])
            continue
        if not isinstance(r, dict):
            continue
        well = str(r.get("well") or r.get("w") or "").strip()
        date = str(r.get("date") or r.get("dt") or "").strip()
        pzab = r.get("pzab") or r.get("p_wf") or r.get("bottomhole_pressure")
        if not well or not date or pzab in (None, ""):
            continue
        qliq = float(r.get("qliq") or r.get("q_liq") or r.get("liquid_rate") or 0)
        out.append([well, date, round(float(pzab), 1), round(qliq, 2)])
    return out


def norm_maps(data: Any) -> dict:
    if isinstance(data, dict) and "maps" in data:
        data = data["maps"]
    return data if isinstance(data, dict) else {}


def norm_ports(data: Any) -> dict:
    if isinstance(data, dict) and "ports" in data:
        data = data["ports"]
    if isinstance(data, list):
        out = {}
        for r in data:
            if not isinstance(r, dict):
                continue
            w = str(r.get("w") or r.get("well") or "").strip()
            if not w:
                continue
            out[w] = {
                "w": w,
                "ports": int(r.get("ports") or r.get("n_ports") or 0),
                "az": float(r.get("az") or r.get("azimuth") or 0),
                "L": float(r.get("L") or r.get("length") or r.get("gs_length") or 0),
            }
        return out
    if isinstance(data, dict):
        out = {}
        for w, r in data.items():
            if isinstance(r, dict):
                out[str(w)] = {
                    "w": str(r.get("w") or w),
                    "ports": int(r.get("ports") or 0),
                    "az": float(r.get("az") or 0),
                    "L": float(r.get("L") or 0),
                }
        return out
    return {}


def path_for(kind: str, layer_id: str = "", field_id: str = "") -> str:
    tpl = ENDPOINTS[kind]
    return tpl.format(layer_id=layer_id, field_id=field_id)


# =============================================================================
# Сборка пакета
# =============================================================================

def pull_layer(layer: dict, datasets: set, date_from: str, date_to: str) -> dict:
    label = layer["label"]
    layer_id = layer["layer_id"]
    print(f"• {label}  layer_id={layer_id}")
    obj: Dict[str, Any] = {
        "layer_id": layer_id,
        "label": label,
        "field_id": CONFIG.get("field_id"),
        "field": CONFIG.get("field"),
    }
    period = {"from": date_from, "to": date_to}

    if "trunks" in datasets:
        raw = api_get(path_for("trunks", layer_id=layer_id))
        obj["trunks"] = norm_trunks(_as_list(raw))
        print(f"  trunks: {len(obj['trunks'])}")

    if "blocks" in datasets:
        raw = api_get(path_for("blocks", layer_id=layer_id))
        obj["blocks"] = norm_blocks(raw)
        print(f"  blocks: {len(obj['blocks'])}")

    if "mor" in datasets:
        raw = api_get(path_for("mor", layer_id=layer_id), period)
        obj["mor"] = norm_mor(_as_list(raw))
        print(f"  mor: {len(obj['mor'])}")

    if "tr" in datasets:
        raw = api_get(path_for("tr", layer_id=layer_id), period)
        obj["tr"] = norm_tr(_as_list(raw))
        print(f"  tr: {len(obj['tr'])}")

    if "maps" in datasets:
        raw = api_get(path_for("maps", layer_id=layer_id), period)
        obj["maps"] = norm_maps(raw)
        print(f"  maps: {len(obj['maps'])}")

    if "grp_ports" in datasets:
        raw = api_get(path_for("grp_ports", layer_id=layer_id))
        obj["grp_ports"] = norm_ports(raw)
        print(f"  grp_ports: {len(obj['grp_ports'])}")

    if "startup" in datasets:
        raw = api_get(path_for("startup", layer_id=layer_id))
        obj["startup"] = raw if isinstance(raw, dict) else {}
        print(f"  startup: {len(obj['startup'])} ключей")

    return obj


def build_package() -> dict:
    datasets = set(CONFIG.get("datasets") or [])
    date_from = CONFIG["date_from"]
    date_to = CONFIG["date_to"]
    layers_cfg = CONFIG.get("layers") or []
    if not layers_cfg:
        raise SystemExit("CONFIG['layers'] пуст — укажите хотя бы один layer_id")

    export: Dict[str, Any] = {
        "schema": "cdp-platform-export",
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"system": "corp_api", "base_url": CONFIG["base_url"]},
        "meta": {
            "do": CONFIG.get("do"),
            "field": CONFIG.get("field"),
            "field_id": CONFIG.get("field_id"),
            "exported_by": CONFIG.get("exported_by"),
        },
        "request": {
            "period": {"date_from": date_from, "date_to": date_to},
            "datasets": sorted(datasets),
            "layers": [{"label": L["label"], "layer_id": L["layer_id"]} for L in layers_cfg],
        },
        "layers": {},
    }

    for layer in layers_cfg:
        export["layers"][layer["label"]] = pull_layer(layer, datasets, date_from, date_to)

    if "history" in datasets:
        field_id = CONFIG.get("field_id") or ""
        print(f"• history  field_id={field_id}")
        raw = api_get(path_for("history", field_id=field_id), {"from": date_from, "to": date_to})
        if isinstance(raw, dict):
            export["history"] = raw
            print(f"  dates: {len(raw.get('dates') or [])}, wells: {len(raw.get('wells') or {})}")
        else:
            print("  history: пусто")

    return export


def save_package(export: dict) -> str:
    out = CONFIG.get("output_json") or "cdp_export.json"
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(out) // 1024
    print(f"\nГотово: {out} ({size_kb} KB)")
    return out


def main() -> int:
    print("Сборка пакета ЦДП…")
    print(f"API: {CONFIG['base_url']}")
    export = build_package()
    save_package(export)
    return 0


# Для Jupyter: просто выполните ячейку с CONFIG и затем:
#   export = build_package(); save_package(export)
if __name__ == "__main__":
    sys.exit(main())
