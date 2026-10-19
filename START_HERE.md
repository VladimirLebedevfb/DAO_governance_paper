# С чего начать

Экспорт проекта на 2026-10-06. Все результаты пересчитываются из этой папки без интернета.

## Главное
- `reports/FINAL_RESULTS.md` - итоговое описание всех результатов для статьи (на английском). Начинать отсюда.
- `reports/new_pipeline_results.md` - технический журнал всех шагов и решений.
- `reports/figures/` - графики для статьи (PNG и PDF, 300 dpi): Figure 2 и Figure 3, распределения размера и рынка, scatter H1, динамика CAR в H3, доходности против BTC в H4.
- `reports/paper_numbers.tex` - все числа статьи как LaTeX-макросы (\\input{paper_numbers}), генерируются кодом.
- `reports/tables/` - все таблицы (`new_*.csv`), воронка выборки `sample_funnel_summary.csv`.
- `reports/sample_funnel.csv` - каждая исключенная организация и причина.
- `data/processed/cross_section.csv` - одна строка на DAO со всеми переменными.
- `config_decisions/token_match_decisions.csv` - решения автора по спорным токенам.

## Как запустить
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_all.py            # новый пайплайн, около 20 секунд, без сети
```
Новый сбор данных (`python -m src.collect.run_collect`) нужен только для обновления данных:
он требует файл `.env` с ключами (шаблон `.env.example`). Лимит CryptoCompare 100 вызовов в месяц.

## Что намеренно не включено
- `.env` - API-ключи.
- `.venv` - окружение Python, восстанавливается командой выше.

## Открытые вопросы
- H3: основной спецификацией предложено считать CAR сверх собственного baseline DAO с кластеризацией.
- Отложенные доработки: типы предложений, перевес голосов, market model, Snapshot, управление во времени.
