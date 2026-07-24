# Подготовка данных для платформы ЦДП

## Зачем

Три сервиса (Закачка, Факторы обводнённости, Запускные параметры) работают от одного JSON-пакета.
Пакет собирается скриптом по `layer_id` / `field_id` и подключается в разделе **Данные**.

## Файлы

| Файл | Назначение |
|------|------------|
| `manifest_datasets.json` | Список необходимых датасетов и полей |
| `config.example.json` | Пример конфига запроса (ID пластов, период, датасеты) |
| `export_data.py` | Скрипт сборки JSON |
| `sample_export.min.json` | Пример структуры пакета |
| `../platform_data.js` | Подключение пакета в браузере (IndexedDB) |

Шаблоны доступны в каталоге платформы → **Данные**.

## Что включать в пакет

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

## Структура JSON

См. `sample_export.min.json`. Корневые поля:

- `schema`: `"cdp-platform-export"`
- `layers.<label>`: trunks, blocks, mor, tr, maps, grp_ports, startup
- `history` (опционально)
- `meta` / `request`: месторождение, период, `layer_id`

## Сборка пакета

```bash
cd data_export
copy config.example.json config.json
# заполните layer_id, field_id, period
python export_data.py --config config.json
```

- `connection.mode: "local_csv"` — из папок пластов репозитория  
- `connection.mode: "corp_api"` — корпоративный API (токен `CDP_DATA_TOKEN`, URL в `CorpApiClient`)

## Подключение в платформе

Каталог → **Данные** → выбрать готовый JSON-файл.