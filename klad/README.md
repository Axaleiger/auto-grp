# Выгрузка данных из КЛАД → платформа ЦДП

## Зачем

Три сервиса (Закачка, Факторы обводнённости, Запускные параметры) работают от одного пакета данных.
Данные готовятся в корпоративной IDE скриптом, который тянет сущности из **КЛАД по `layer_id` / `field_id`**, пишет JSON, его отправляют на почту и загружают в каталог платформы.

## Файлы

| Файл | Назначение |
|------|------------|
| `manifest_datasets.json` | Полный список необходимых датасетов и полей |
| `config.example.json` | Шаблон запроса (ID пластов, период, список датасетов) |
| `export_from_klad.py` | Скрипт выгрузки |
| `../platform_data.js` | Загрузка JSON в браузере (IndexedDB) |
| `out/cdp_export.json` | Результат выгрузки (создаётся скриптом) |

## Что выгружать (кратко)

| Датасет | Закачка | Факторы | Запускные |
|---------|:-------:|:-------:|:---------:|
| trunks (стволы) | ✓ | ✓ | |
| blocks (блоки) | ✓ | ✓ | |
| mor (МЭР) | ✓ | ✓ | |
| tr (техрежим Pзаб) | | ○ | |
| maps (карты Pпл) | | ✓ | |
| grp_ports (порты МГРП) | | ○ | ○ |
| history (история) | | ○ | |
| startup (ПВТ/глубины) | | | ○ |

✓ обязательно · ○ желательно

Подробная схема полей — в `manifest_datasets.json`.

## Вид JSON для платформы

```json
{
  "schema": "cdp-platform-export",
  "version": "1.0",
  "exported_at": "2026-07-24T09:00:00Z",
  "source": { "system": "KLAD" },
  "meta": { "do": "Хантос", "field": "Романовское", "field_id": "..." },
  "request": {
    "period": { "date_from": "2024-01-01", "date_to": "2026-06-01" },
    "datasets": ["trunks", "blocks", "mor", "tr", "maps", "grp_ports", "history", "startup"],
    "layers": [{ "label": "2БС10", "layer_id": "..." }]
  },
  "layers": {
    "2БС10": {
      "layer_id": "...",
      "label": "2БС10",
      "trunks": [{ "w": "123", "x": 0, "y": 0, "hz": true, "x3": 1, "y3": 1 }],
      "blocks": { "Блок-1": [[x, y], [x, y]] },
      "mor": [["123", "01.01.2026", 1000, 800, 200]],
      "tr": [["123", "01.01.2026", 120, 50]],
      "maps": { "2026_01_....grd": { "label": "...", "nx": 0, "ny": 0, "xmin": 0, "xmax": 0, "ymin": 0, "ymax": 0, "step": 3, "data": [] } },
      "grp_ports": { "123": { "w": "123", "ports": 5, "az": 90, "L": 400 } },
      "startup": { "kh": 10, "h": 8, "Pi": 180, "Pwf": 60, "Gf": 80, "Hform": 2500, "Hpump": 2200 }
    }
  },
  "history": { "dates": ["01.01.2024"], "wells": { "123": { "liq": [0], "oil": [0] } } }
}
```

## Как выгрузить из КЛАД

```bash
cd klad
copy config.example.json config.json
# заполните layer_id, field_id, period
python export_from_klad.py --config config.json
```

- `connection.mode: "local_csv"` — демо из папок пластов репозитория  
- `connection.mode: "klad_api"` — боевой режим; токен в `KLAD_TOKEN`, допишите URL в `KladApiClient`

## Как загрузить в платформу

1. Откройте `index.html` → боковая кнопка **Данные**
2. Выберите `cdp_export.json`
3. Сервисы «Закачка» и «Факторы обводнённости» подхватят пакет из IndexedDB автоматически
