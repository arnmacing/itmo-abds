# ЭнергоСбыт

[![labs](https://github.com/arnmacing/itmo-abds/actions/workflows/energosbyt.lab.yml/badge.svg)](https://github.com/arnmacing/itmo-abds/actions/workflows/energosbyt.lab.yml)

Backend-сервис лабораторной ЖКХ-компании для практики по курсу «Архитектура систем обработки больших данных».
Лабораторная работа №1: SCD в ClickHouse. Требования к репозиторию и процессу сдачи - в [CONTRIBUTING.md](CONTRIBUTING.md).

## Запуск

Нужны Docker и Python 3.11+.

| Команда | Что делает |
| --- | --- |
| `make run` | Поднимает ClickHouse и приложение через `docker compose` |
| `make setup` | Создаёт схему, генерирует и загружает данные. Требует `make run` |
| `make gen` | Генерирует датасеты в `data/` |
| `make load` | Загружает CSV из `data/` в ClickHouse |
| `make teardown` | Удаляет таблицы и данные |
| `make stop` | Останавливает контейнеры |
| `make clean` | То же, что `stop`, плюс удаление docker-томов. Папка `volume/` с данными ClickHouse остаётся, её можно удалить вручную |

Порядок:

```bash
make run
make setup
curl http://localhost:8080/ping
make teardown
make stop
```

`make setup` в идеале занимает около 5 секунд: генерация 2 с и загрузка 2 с.

## Конфигурация

Все параметры берутся из `.env.local`.

| Переменная | Значение | Описание |
| --- | --- | --- |
| `APP_PORT` | `8080` | Порт HTTP-сервиса |
| `CLICKHOUSE_HOST` | `localhost` | Адрес ClickHouse с хоста. Контейнер приложения ходит по имени сервиса `clickhouse`, это задано в `docker-compose.yml` |
| `CLICKHOUSE_PORT` | `9000` | Нативный протокол |
| `CLICKHOUSE_HTTP_PORT` | `8123` | HTTP-интерфейс, его используют загрузчик и приложение |
| `CLICKHOUSE_USER` | `default` | Пользователь |
| `CLICKHOUSE_PASSWORD` | `supadupapwd` | Пароль, учебный, секретом не является |
| `CLICKHOUSE_DATABASE` | `energosbyt` | База данных, создаётся образом при первом старте |

Данные ClickHouse хранятся в `volume/`, датасеты в `data/`. Обе папки в `.gitignore`.

## API

Сервис на FastAPI, код в `app/` разбит по слоям: клиент ClickHouse, модели, репозиторий, сервисы и роуты. После `make run` доступна документация Swagger: http://localhost:8080/docs.
Схема OpenAPI сохранена в [`api/openapi.json`](api/openapi.json).

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/ping` | Проверка доступности |
| `GET` | `/users/{id}` | Собственник |
| `PATCH` | `/users/{id}` | Изменение ФИО (SCD 1) и телефона (SCD 3) |
| `GET` | `/realty/{id}` | Объект недвижимости |
| `POST` | `/realty/{id}/readings` | Передача показания, повтор за дату создаёт корректировку |
| `GET` | `/realty/{id}/readings?date_from=&date_to=` | Актуальные показания за период |
| `GET` | `/realty/{id}/invoices?limit=&offset=` | Счета объекта, новые сверху |
| `GET` | `/tariffs?date=` | Версия тарифа на дату |
| `POST` | `/realty/{id}/gauges` | Установка счётчика, старая установка аннулируется |

Ошибки возвращаются как `{"message": "..."}`: `400` для невалидных полей и параметров, `404` если объект не найден.

## Схема данных

Схема создаётся скриптом `sql/schema.sql`, удаляется `sql/teardown.sql`. Движки заданы заданием, ключи сортировки и партиционирование выбраны так:

| Таблица | Движок | ORDER BY | PARTITION BY | Почему |
| --- | --- | --- | --- | --- |
| `dim_realty` | `MergeTree` | `id` | - | Точечный поиск по идентификатору, 1 000 строк |
| `dim_gauges` | `MergeTree` | `id` | - | То же |
| `dim_users` | `ReplacingMergeTree(updated_at)` | `id` | - | Одна актуальная строка на собственника, побеждает последняя по `updated_at` |
| `dim_tariffs` | `ReplacingMergeTree(updated_at)` | `(id, valid_from)` | - | Пара однозначно задаёт версию SCD 2. Закрыть открытую версию можно вставкой строки с тем же ключом и новым `valid_to` |
| `fact_gauge_bindings` | `VersionedCollapsingMergeTree(sign, version)` | `(realty_id, gauge_id, version)` | - | В ключе только поля, по которым схлопываются пары установка/аннулирование. `created_at` в ключ не входит, иначе аннулирующая строка не совпадёт с аннулируемой |
| `fact_meter_readings` | `ReplacingMergeTree(created_at)` | `(realty_id, reading_date)` | `toYYYYMM(reading_date)` | Корректировка за дату заменяет старую строку независимо от счётчика. Запросы идут по объекту за диапазон дат, партиции по месяцам отсекают лишние куски |
| `fact_invoice` | `MergeTree` | `(realty_id, created_at)` | `toYear(created_at)` | Выборка счетов объекта с сортировкой по дате и пагинацией |

## Данные

`make gen` запускает `gen/generate.py` и пишет CSV с заголовком в `data/`. Генерация детерминирована, повторный запуск даёт те же файлы.

| Таблица | Строк | Что внутри |
| --- | --- | --- |
| `dim_realty` | 1 000 | Пять домов, 90% квартир и 10% нежилых помещений |
| `dim_gauges` | 1 049 | Счётчик на объект плюс замены |
| `dim_tariffs` | 3 | Три версии тарифа «День-Ночь», открытая до `2099-01-01` |
| `dim_users` | 1 000 | Собственник на объект, у 10% заполнен `phone_prev` |
| `fact_gauge_bindings` | 1 098 | Установка на каждый объект, у 49 объектов аннулирование и новая установка с `version = 2` |
| `fact_meter_readings` | 1 129 033 | Показание на каждый объект за каждый день с 2023-11-01 по 2026-10-31, 3% с корректировкой |
| `fact_invoice` | 36 000 | Счёт на объект за каждый из 36 месяцев, цена по версии тарифа этого месяца, `deadline` 10-е число следующего месяца |

`make load` запускает `scripts/load.sh`: по HTTP делает `TRUNCATE` каждой таблицы и затем `INSERT ... FORMAT CSVWithNames`.
Повторная загрузка не создаёт дублей, потому что всегда начинается с пустых таблиц.
Побочный эффект: изменения, сделанные через API после загрузки, при повторном `make load` теряются.

Корректировки показаний и пары установка/аннулирование ClickHouse схлопывает уже при вставке, если они попали в один блок.
Поэтому `count()` без `FINAL` показывает 1 096 000 показаний и 1 000 привязок сразу после загрузки.

## Сценарии SCD

Все сценарии из задания выполнены вручную через API и SQL. Для каждого в [docs/scenarios.md](docs/scenarios.md) приведены запросы, их вывод и что он показывает:

- собственник сменил фамилию (SCD 1);
- собственник сменил телефон дважды (SCD 3);
- изменился тариф с 1 ноября (SCD 2);
- пересчёт счёта за старый месяц (SCD 2);
- корректировка показания (ReplacingMergeTree);
- замена счётчика (VersionedCollapsingMergeTree);
- ошибочная строка с лишним нулём (DELETE).

## Структура репозитория

```
.
├── app/
│   ├── main.py         # сборка приложения и обработка ошибок
│   ├── routes.py       # эндпоинты и проверка запросов
│   ├── services.py     # логика SCD и проверки существования
│   ├── repository.py   # SQL-запросы
│   ├── models.py       # тела запросов
│   └── db.py           # клиент ClickHouse
├── gen/generate.py     # генератор датасетов
├── scripts/load.sh     # загрузка CSV в ClickHouse
├── sql/schema.sql      # создание таблиц
├── sql/teardown.sql    # удаление таблиц
├── api/openapi.json    # схема API
├── docs/scenarios.md   # сценарии SCD с SQL
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── .env.local
```
