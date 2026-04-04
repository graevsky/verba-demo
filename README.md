# Verba demo

Парсер для Wildberries в качестве тестового для Verba-group.

- Собирает каталог товаров из поиска по запросу;
- Собирает карточки товаров и detail
- Сохраняет полный каталог в Excel
- Дополнительно фильтр согласно ТЗ

## Установка

### 1. Создать и активировать venv

```cmd
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Установить зависимости

```bash
pip install pandas openpyxl curl-cffi playwright
```

### 3. Установить chromium для playwright

```bash
playwright install chromium
```

После выполнения появятся файлы:

- `product_list.xlsx` — полный каталог
- `product_list_filtered.xlsx` — отфильтрованный каталог

При появлении ошибок 429 стоит повторно перезапустить парсер через какое то время.
