#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт выгрузки данных из КЛАДа и формирования JSON-пакета для платформы ЦДП.
Предназначен для запуска в IDE / Jupyter.

Порядок подготовки:
  1. Открыть настоящий файл в IDE или Jupyter.
  2. Заполнить блок «НАИМЕНОВАНИЯ ИЗ КЛАДА».
     Необходимо запросить точные наименования сущностей / таблиц / датасетов
     в КЛАДе и указать их в соответствующих переменных NAME_*.
  3. Заполнить параметры подключения (URL, токен), идентификаторы пластов
     (layer_id) и период выгрузки.
  4. При необходимости указать наименования колонок (FIELD_*).
  5. Выполнить скрипт. Результат: файл cdp_export.json.
  6. Подключить полученный JSON в платформе: каталог → раздел «Данные».

Требования: Python 3 (стандартная библиотека). Внешние пакеты не требуются.
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
# НАИМЕНОВАНИЯ ИЗ КЛАДА
# Необходимо запросить точные наименования сущностей в КЛАДе и указать их ниже
# (строковые значения в кавычках).
# Пустое значение ("") означает, что соответствующий блок данных не запрашивается.
# =============================================================================

# --- Стволы / координаты скважин ---
# Содержание: номер скважины; координаты устья / Т1 (X, Y); для ГС — Т3 (X3, Y3).
# Потребители: сервисы «Закачка», «Факторы обводнённости».
NAME_TRUNKS = ""  # Необходимо указать наименование из КЛАДа (стволы / координаты)

# --- Контуры блоков разработки ---
# Содержание: наименование блока; полигон контура (перечень точек X, Y).
# Потребители: сервисы «Закачка», «Факторы обводнённости».
NAME_BLOCKS = ""  # Необходимо указать наименование из КЛАДа (блоки / контуры)

# --- МЭР (месячный эксплуатационный рапорт) ---
# Содержание: скважина; дата отчёта; закачка, м³/мес; жидкость, т/мес; нефть, т/мес.
# Даты, как правило, помесячные (например: 01.01.2024, 01.02.2024 и далее).
# Потребители: сервисы «Закачка», «Факторы обводнённости».
NAME_MER = ""  # Необходимо указать наименование из КЛАДа (МЭР / месячные показатели)

# --- Техрежим / забойное давление ---
# Содержание: скважина; дата; Pзаб, атм; при наличии — дебит жидкости.
# Потребитель: сервис «Факторы обводнённости».
NAME_TR = ""  # Необходимо указать наименование из КЛАДа (техрежим / Pзаб)

# --- Карты пластового давления ---
# Содержание: по датам — сетки / значения Pпл по пласту.
# Потребитель: сервис «Факторы обводнённости» (карты давления).
NAME_MAPS_PPL = ""  # Необходимо указать наименование из КЛАДа (карты Pпл)

# --- Порты МГРП / автоГРП ---
# Содержание: по скважине — число портов; азимут ГС; длина ГС.
# Потребитель: сервис «Факторы обводнённости».
NAME_GRP_PORTS = ""  # Необходимо указать наименование из КЛАДа (порты ГРП / МГРП)

# --- История добычи по месторождению ---
# Содержание: ряд дат; по скважинам — ряды Qo, Qж, обводнённость.
# Потребитель: сервис «Факторы обводнённости» (история).
NAME_HISTORY = ""  # Необходимо указать наименование из КЛАДа (история добычи)

# --- Запускные параметры скважин ---
# Содержание: исходные (базовые) параметры для расчёта запускных показателей.
# Потребитель: сервис «Запускные параметры».
NAME_STARTUP = ""  # Необходимо указать наименование из КЛАДа (запускные параметры)

# --- Наименования полей (колонок) в ответах КЛАДа ---
# Необходимо запросить точные наименования колонок в КЛАДе и указать их ниже,
# если они отличаются от стандартных вариантов, используемых при нормализации.
# Пустая строка — применяются запасные наименования в коде нормализации.
FIELD_WELL = ""       # Необходимо указать наименование колонки «скважина» из КЛАДа
FIELD_DATE = ""       # Необходимо указать наименование колонки «дата» из КЛАДа
FIELD_INJ = ""        # Необходимо указать наименование колонки «закачка» (МЭР) из КЛАДа
FIELD_LIQ = ""        # Необходимо указать наименование колонки «жидкость» (МЭР) из КЛАДа
FIELD_OIL = ""        # Необходимо указать наименование колонки «нефть» (МЭР) из КЛАДа
FIELD_PZAB = ""       # Необходимо указать наименование колонки «Pзаб» из КЛАДа
FIELD_X = ""          # Необходимо указать наименование колонки координаты X из КЛАДа
FIELD_Y = ""          # Необходимо указать наименование колонки координаты Y из КЛАДа
FIELD_PORTS = ""      # Необходимо указать наименование колонки «число портов» из КЛАДа
FIELD_AZIMUTH = ""    # Необходимо указать наименование колонки «азимут» из КЛАДа
FIELD_GS_LEN = ""     # Необходимо указать наименование колонки «длина ГС» из КЛАДа

# =============================================================================
# ПОДКЛЮЧЕНИЕ И ПАРАМЕТРЫ ЗАПРОСА
# =============================================================================

CONFIG = {
    # Базовый URL API КЛАДа (без завершающего слэша)
    "base_url": "https://data.example.corp/api",

    # Токен доступа: значение в данной строке либо переменная окружения
    "token": "",                      # пример: "eyJ..."
    "token_env": "CDP_DATA_TOKEN",

    "timeout_sec": 120,

    # Метаданные пакета (справочные; не обязательно совпадают с КЛАДом)
    "do": "Хантос",
    "field": "Романовское",
    "field_id": "",                   # Необходимо указать идентификатор месторождения в КЛАДе (при наличии)
    "exported_by": "",

    # Период выгрузки (МЭР, техрежим, карты, история)
    "date_from": "2024-01-01",
    "date_to": "2026-06-01",

    # Пласты: label — отображаемое наименование в платформе; layer_id — идентификатор пласта в КЛАДе
    "layers": [
        {"label": "2БС10", "layer_id": ""},   # Необходимо указать layer_id пласта 2БС10 из КЛАДа
        {"label": "БС9/1", "layer_id": ""},   # Необходимо указать layer_id пласта БС9/1 из КЛАДа
    ],

    "output_json": "cdp_export.json",
}

# Шаблоны URL. Подстановки: {name} — из NAME_*; {layer_id} / {field_id} — из CONFIG.
# При иной структуре API необходимо уточнить пути у владельцев API и скорректировать шаблоны.
ENDPOINTS = {
    "by_name_layer": "/datasets/{name}?layer_id={layer_id}",
    "by_name_field": "/datasets/{name}?field_id={field_id}",
}

# Справочник блоков данных (для протокола выгрузки и сборки пакета).
# Изменение без необходимости не рекомендуется.
DATASETS_INFO = [
    {
        "key": "trunks",
        "name_var": "NAME_TRUNKS",
        "title_ru": "Стволы / координаты",
        "desc_ru": "Скважина, X/Y устья (Т1), для ГС — X3/Y3 (Т3).",
        "has_dates": False,
        "scope": "layer",
    },
    {
        "key": "blocks",
        "name_var": "NAME_BLOCKS",
        "title_ru": "Контуры блоков",
        "desc_ru": "Имя блока и полигон контура (точки X, Y).",
        "has_dates": False,
        "scope": "layer",
    },
    {
        "key": "mor",
        "name_var": "NAME_MER",
        "title_ru": "МЭР (месячные показатели)",
        "desc_ru": "Скважина + дата + закачка + жидкость + нефть (помесячно).",
        "has_dates": True,
        "scope": "layer",
    },
    {
        "key": "tr",
        "name_var": "NAME_TR",
        "title_ru": "Техрежим / Pзаб",
        "desc_ru": "Скважина + дата + забойное давление (+ опц. дебит жидкости).",
        "has_dates": True,
        "scope": "layer",
    },
    {
        "key": "maps",
        "name_var": "NAME_MAPS_PPL",
        "title_ru": "Карты пластового давления",
        "desc_ru": "По датам — значения / сетки Pпл по пласту.",
        "has_dates": True,
        "scope": "layer",
    },
    {
        "key": "grp_ports",
        "name_var": "NAME_GRP_PORTS",
        "title_ru": "Порты МГРП",
        "desc_ru": "По скважине: число портов, азимут, длина ГС.",
        "has_dates": False,
        "scope": "layer",
    },
    {
        "key": "startup",
        "name_var": "NAME_STARTUP",
        "title_ru": "Запускные параметры",
        "desc_ru": "Дефолтные параметры для калькулятора запускных скважин.",
        "has_dates": False,
        "scope": "layer",
    },
    {
        "key": "history",
        "name_var": "NAME_HISTORY",
        "title_ru": "История добычи",
        "desc_ru": "Ряд дат и по скважинам Qo / Qж / обводнённость.",
        "has_dates": True,
        "scope": "field",
    },
]

# =============================================================================
# Внутренняя логика (изменение без необходимости не рекомендуется)
# =============================================================================

_NAME_BY_KEY = {
    "trunks": lambda: NAME_TRUNKS,
    "blocks": lambda: NAME_BLOCKS,
    "mor": lambda: NAME_MER,
    "tr": lambda: NAME_TR,
    "maps": lambda: NAME_MAPS_PPL,
    "grp_ports": lambda: NAME_GRP_PORTS,
    "startup": lambda: NAME_STARTUP,
    "history": lambda: NAME_HISTORY,
}


def _klad_name(key: str) -> str:
    fn = _NAME_BY_KEY.get(key)
    return (fn() if fn else "").strip()


def _col(*candidates: str) -> List[str]:
    """Приоритет: явное имя из FIELD_* , затем запасные варианты."""
    out: List[str] = []
    for c in candidates:
        c = (c or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def _pick(row: dict, names: List[str], default: Any = None) -> Any:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return default


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
            "User-Agent": "cdp-pull-data/1.1",
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


def path_for(klad_name: str, scope: str, layer_id: str = "", field_id: str = "") -> str:
    tpl = ENDPOINTS["by_name_field" if scope == "field" else "by_name_layer"]
    return tpl.format(name=klad_name, layer_id=layer_id, field_id=field_id)


# --- Нормализация ответов → формат пакета платформы ---

def norm_trunks(rows: list) -> list:
    well_keys = _col(FIELD_WELL, "w", "well", "well_name", "name")
    x_keys = _col(FIELD_X, "x", "x1", "t1_x")
    y_keys = _col(FIELD_Y, "y", "y1", "t1_y")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        w = str(_pick(r, well_keys) or "").strip()
        if not w:
            continue
        item = {
            "w": w,
            "x": float(_pick(r, x_keys, 0) or 0),
            "y": float(_pick(r, y_keys, 0) or 0),
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
                out[str(bid)] = [
                    [float(p[0]), float(p[1])]
                    for p in pts
                    if isinstance(p, (list, tuple)) and len(p) >= 2
                ]
        return out
    return {}


def norm_mor(rows: list) -> list:
    well_keys = _col(FIELD_WELL, "well", "w", "well_name")
    date_keys = _col(FIELD_DATE, "date", "dt")
    inj_keys = _col(FIELD_INJ, "inj", "injection", "zakachka")
    liq_keys = _col(FIELD_LIQ, "liq", "liquid", "fluid")
    oil_keys = _col(FIELD_OIL, "oil", "oil_prod")
    out = []
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 5:
            out.append([str(r[0]), str(r[1]), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0)])
            continue
        if not isinstance(r, dict):
            continue
        well = str(_pick(r, well_keys) or "").strip()
        date = str(_pick(r, date_keys) or "").strip()
        inj = float(_pick(r, inj_keys, 0) or 0)
        liq = float(_pick(r, liq_keys, 0) or 0)
        oil = float(_pick(r, oil_keys, 0) or 0)
        if well and date:
            out.append([well, date, round(inj, 1), round(liq, 1), round(oil, 1)])
    return out


def norm_tr(rows: list) -> list:
    well_keys = _col(FIELD_WELL, "well", "w")
    date_keys = _col(FIELD_DATE, "date", "dt")
    pzab_keys = _col(FIELD_PZAB, "pzab", "p_wf", "bottomhole_pressure")
    out = []
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 3:
            qliq = float(r[3]) if len(r) > 3 else 0.0
            out.append([str(r[0]), str(r[1]), float(r[2]), round(qliq, 2)])
            continue
        if not isinstance(r, dict):
            continue
        well = str(_pick(r, well_keys) or "").strip()
        date = str(_pick(r, date_keys) or "").strip()
        pzab = _pick(r, pzab_keys)
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
    well_keys = _col(FIELD_WELL, "w", "well")
    ports_keys = _col(FIELD_PORTS, "ports", "n_ports")
    az_keys = _col(FIELD_AZIMUTH, "az", "azimuth")
    len_keys = _col(FIELD_GS_LEN, "L", "length", "gs_length")
    if isinstance(data, dict) and "ports" in data:
        data = data["ports"]
    if isinstance(data, list):
        out = {}
        for r in data:
            if not isinstance(r, dict):
                continue
            w = str(_pick(r, well_keys) or "").strip()
            if not w:
                continue
            out[w] = {
                "w": w,
                "ports": int(_pick(r, ports_keys, 0) or 0),
                "az": float(_pick(r, az_keys, 0) or 0),
                "L": float(_pick(r, len_keys, 0) or 0),
            }
        return out
    if isinstance(data, dict):
        out = {}
        for w, r in data.items():
            if isinstance(r, dict):
                out[str(w)] = {
                    "w": str(_pick(r, well_keys, w) or w),
                    "ports": int(_pick(r, ports_keys, 0) or 0),
                    "az": float(_pick(r, az_keys, 0) or 0),
                    "L": float(_pick(r, len_keys, 0) or 0),
                }
        return out
    return {}


_NORM = {
    "trunks": lambda raw: norm_trunks(_as_list(raw)),
    "blocks": norm_blocks,
    "mor": lambda raw: norm_mor(_as_list(raw)),
    "tr": lambda raw: norm_tr(_as_list(raw)),
    "maps": norm_maps,
    "grp_ports": norm_ports,
    "startup": lambda raw: raw if isinstance(raw, dict) else {},
}


def print_plan() -> None:
    print("План выгрузки (заполненные наименования из КЛАДа):\n")
    any_filled = False
    for ds in DATASETS_INFO:
        name = _klad_name(ds["key"])
        mark = "✓" if name else "·"
        dates = " [содержит даты; применяется период]" if ds["has_dates"] else ""
        print(f"  {mark} {ds['title_ru']}")
        print(f"      {ds['desc_ru']}{dates}")
        if name:
            any_filled = True
            print(f"      наименование в КЛАДе: «{name}»")
        else:
            print(
                f"      наименование в КЛАДе: не указано — блок не запрашивается"
                f"  ({ds['name_var']})"
            )
        print()
    if not any_filled:
        raise SystemExit(
            "Не заполнено ни одно наименование NAME_*.\n"
            "Необходимо запросить точные наименования сущностей в КЛАДе "
            "и указать их в блоке «НАИМЕНОВАНИЯ ИЗ КЛАДА»."
        )


def pull_layer(layer: dict, date_from: str, date_to: str) -> dict:
    label = layer["label"]
    layer_id = (layer.get("layer_id") or "").strip()
    if not layer_id:
        raise SystemExit(
            f"Для пласта «{label}» не указан layer_id. "
            "Необходимо указать идентификатор пласта из КЛАДа."
        )
    print(f"• Пласт {label}  (layer_id={layer_id})")
    obj: Dict[str, Any] = {
        "layer_id": layer_id,
        "label": label,
        "field_id": CONFIG.get("field_id"),
        "field": CONFIG.get("field"),
    }
    period = {"from": date_from, "to": date_to}

    for ds in DATASETS_INFO:
        if ds["scope"] != "layer":
            continue
        key = ds["key"]
        name = _klad_name(key)
        if not name:
            continue
        params = period if ds["has_dates"] else None
        print(f"  → {ds['title_ru']}  «{name}»")
        raw = api_get(path_for(name, "layer", layer_id=layer_id), params)
        obj[key] = _NORM[key](raw)
        n = len(obj[key]) if hasattr(obj[key], "__len__") else "?"
        print(f"     получено: {n}")

    return obj


def build_package() -> dict:
    print_plan()
    date_from = CONFIG["date_from"]
    date_to = CONFIG["date_to"]
    layers_cfg = CONFIG.get("layers") or []
    if not layers_cfg:
        raise SystemExit(
            "Список CONFIG['layers'] пуст. "
            "Необходимо указать не менее одного пласта с layer_id из КЛАДа."
        )

    filled_keys = [ds["key"] for ds in DATASETS_INFO if _klad_name(ds["key"])]

    export: Dict[str, Any] = {
        "schema": "cdp-platform-export",
        "version": "1.1",
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"system": "klad", "base_url": CONFIG["base_url"]},
        "meta": {
            "do": CONFIG.get("do"),
            "field": CONFIG.get("field"),
            "field_id": CONFIG.get("field_id"),
            "exported_by": CONFIG.get("exported_by"),
        },
        "request": {
            "period": {"date_from": date_from, "date_to": date_to},
            "datasets": filled_keys,
            "klad_names": {k: _klad_name(k) for k in filled_keys},
            "layers": [
                {"label": L["label"], "layer_id": L.get("layer_id")} for L in layers_cfg
            ],
        },
        "layers": {},
    }

    for layer in layers_cfg:
        export["layers"][layer["label"]] = pull_layer(layer, date_from, date_to)

    hist_name = _klad_name("history")
    if hist_name:
        field_id = (CONFIG.get("field_id") or "").strip()
        print(f"• История добычи  «{hist_name}»  (field_id={field_id or '—'})")
        raw = api_get(
            path_for(hist_name, "field", field_id=field_id),
            {"from": date_from, "to": date_to},
        )
        if isinstance(raw, dict):
            export["history"] = raw
            print(f"  dates: {len(raw.get('dates') or [])}, wells: {len(raw.get('wells') or {})}")
        else:
            print("  История: данные отсутствуют либо формат ответа не соответствует ожидаемому.")

    return export


def save_package(export: dict) -> str:
    out = CONFIG.get("output_json") or "cdp_export.json"
    out = os.path.abspath(out)
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(out) // 1024
    print(f"\nФормирование завершено: {out} ({size_kb} KB)")
    return out


def main() -> int:
    print("Формирование пакета ЦДП на основе данных КЛАДа…")
    print(f"API: {CONFIG['base_url']}")
    print(f"Период: {CONFIG['date_from']} — {CONFIG['date_to']}\n")
    export = build_package()
    save_package(export)
    return 0


# Для Jupyter: выполнить ячейки с NAME_* / CONFIG, затем:
#   export = build_package(); save_package(export)
if __name__ == "__main__":
    sys.exit(main())
