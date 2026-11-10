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

Сервис на FastAPI, код в `app/main.py`. После `make run` доступна документация Swagger: http://localhost:8080/docs.
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

Все сценарии выполнены на загруженных данных. SQL запускался так:

```bash
docker compose exec clickhouse clickhouse-client --password supadupapwd --query "..."
```

### Собственник сменил фамилию (SCD 1)

```bash
curl -X PATCH localhost:8080/users/1 -H 'Content-Type: application/json' -d '{"fio":"Петрова Анна Сергеевна"}'
curl localhost:8080/users/1
# {"id":1,"fio":"Петрова Анна Сергеевна","phone":"+79011063465","phone_prev":""}
```

```sql
SELECT fio, updated_at FROM energosbyt.dim_users FINAL WHERE id = 1
-- Петрова Анна Сергеевна  2026-11-10 19:10:16

SELECT fio, updated_at FROM energosbyt.dim_users WHERE id = 1 ORDER BY updated_at
-- Иванов Михаил Петрович  2023-10-15 12:00:00
-- Петрова Анна Сергеевна  2026-11-10 19:10:16

OPTIMIZE TABLE energosbyt.dim_users FINAL
SELECT fio FROM energosbyt.dim_users WHERE id = 1
-- Петрова Анна Сергеевна
```

Сервис вставляет новую строку с тем же `id` и свежим `updated_at`. С `FINAL` видна только она.
Без `FINAL` до слияния физически лежат обе строки, после `OPTIMIZE` старая фамилия исчезает из таблицы.

### Собственник сменил телефон дважды (SCD 3)

```bash
curl -X PATCH localhost:8080/users/1 -H 'Content-Type: application/json' -d '{"phone":"+79111111111"}'
curl -X PATCH localhost:8080/users/1 -H 'Content-Type: application/json' -d '{"phone":"+79222222222"}'
curl localhost:8080/users/1
# {"id":1,"fio":"Петрова Анна Сергеевна","phone":"+79222222222","phone_prev":"+79111111111"}
```

```sql
SELECT phone, phone_prev FROM energosbyt.dim_users FINAL WHERE id = 1
-- +79222222222  +79111111111
```

При смене телефона текущее значение переезжает в `phone_prev`. Хранится ровно одно предыдущее значение, первый телефон `+79011063465` потерян, это и есть SCD 3.

### Изменился тариф с 1 ноября (SCD 2)

```bash
curl 'localhost:8080/tariffs?date=2025-10-31'
# {"id":1,"name":"День-Ночь","price_day_kwph":600,"price_night_kwph":300,"valid_from":"2024-11-01 00:00:00","valid_to":"2025-11-01 00:00:00"}
curl 'localhost:8080/tariffs?date=2025-11-01'
# {"id":1,"name":"День-Ночь","price_day_kwph":620,"price_night_kwph":310,"valid_from":"2025-11-01 00:00:00","valid_to":"2099-01-01 00:00:00"}
```

```sql
SELECT price_day_kwph, price_night_kwph, valid_from, valid_to FROM energosbyt.dim_tariffs FINAL ORDER BY valid_from
-- 560  280  2023-11-01 00:00:00  2024-11-01 00:00:00
-- 600  300  2024-11-01 00:00:00  2025-11-01 00:00:00
-- 620  310  2025-11-01 00:00:00  2099-01-01 00:00:00
```

Каждая версия тарифа - отдельная строка с интервалом действия. Запрос на дату выбирает строку по условию `valid_from <= date < valid_to`.

### Пересчёт счёта за старый месяц (SCD 2)

Счёт объекта 1 за октябрь 2024, выставлен 1 ноября 2024 по версии 560/280:

```sql
SELECT day_kw, night_kw, price, deadline, created_at FROM energosbyt.fact_invoice WHERE realty_id = 1 AND deadline = '2024-11-10'
-- 238  48  146720  2024-11-10  2024-11-01 09:00:00
```

Пересчёт - новый счёт с той же версией тарифа, что действовала в расчётном месяце:

```sql
INSERT INTO energosbyt.fact_invoice
SELECT i.realty_id, i.user_id, i.tariff_id, i.gauge_id, i.day_kw, i.night_kw,
       i.day_kw * t.price_day_kwph + i.night_kw * t.price_night_kwph, i.deadline, now()
FROM energosbyt.fact_invoice i
JOIN energosbyt.dim_tariffs t ON t.id = i.tariff_id
WHERE i.realty_id = 1 AND i.deadline = '2024-11-10'
  AND addMonths(i.created_at, -1) >= t.valid_from AND addMonths(i.created_at, -1) < t.valid_to

SELECT price, created_at FROM energosbyt.fact_invoice WHERE realty_id = 1 AND deadline = '2024-11-10' ORDER BY created_at
-- 146720  2024-11-01 09:00:00
-- 146720  2026-11-10 19:10:58

SELECT 238 * price_day_kwph + 48 * price_night_kwph FROM energosbyt.dim_tariffs FINAL WHERE valid_to = '2099-01-01 00:00:00'
-- 162440
```

Старый счёт не изменился. Пересчитанный счёт получил ту же сумму 146720, потому что цена взята из версии на дату счёта, а не из текущей версии, которая дала бы 162440.

### Корректировка показания (ReplacingMergeTree)

```bash
curl -X POST localhost:8080/realty/1/readings -H 'Content-Type: application/json' \
  -d '{"user_id":1,"gauge_id":1,"tariff_id":1,"reading_date":"2026-10-01","day_kw":9000,"night_kw":2200}'
curl 'localhost:8080/realty/1/readings?date_from=2026-10-01&date_to=2026-10-01'
# {"readings":[{"reading_date":"2026-10-01","user_id":1,"tariff_id":1,"gauge_id":1,"day_kw":9000,"night_kw":2200}],"count":1}
```

```sql
SELECT day_kw, night_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 1 AND reading_date = '2026-10-01' ORDER BY created_at
-- 8669  2170  2026-10-01 10:00:00
-- 9000  2200  2026-11-10 19:10:17

SELECT day_kw, night_kw, created_at FROM energosbyt.fact_meter_readings FINAL WHERE realty_id = 1 AND reading_date = '2026-10-01'
-- 9000  2200  2026-11-10 19:10:17
```

Старая строка остаётся в таблице, сервис читает с `FINAL` и отдаёт одно значение за дату, с последним `created_at`.

### Замена счётчика (VersionedCollapsingMergeTree)

```bash
curl -X POST localhost:8080/realty/1/gauges -H 'Content-Type: application/json' -d '{"gauge_id":2}'
```

```sql
SELECT gauge_id, sign, version, created_at FROM energosbyt.fact_gauge_bindings WHERE realty_id = 1 ORDER BY version, sign DESC
-- 1   1  1  2023-10-15 12:00:00
-- 1  -1  1  2026-11-10 19:10:18
-- 2   1  2  2026-11-10 19:10:18

SELECT gauge_id, sign, version FROM energosbyt.fact_gauge_bindings FINAL WHERE realty_id = 1
-- 2  1  2
```

Сервис вставил строку аннулирования с `sign = -1` и тем же `version = 1`, что у активной установки, и новую установку с `version = 2`.
После `FINAL` пара схлопнулась, активной осталась только установка счётчика 2.

### Ошибочная строка с лишним нулём (DELETE)

Показание 90000 вместо 9000 для объекта 3 за 2026-10-05:

```sql
SELECT day_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05' ORDER BY created_at
-- 16350  2026-10-05 10:00:00
-- 90000  2026-11-10 19:10:18

DELETE FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05' AND day_kw = 90000

SELECT day_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05'
-- 16350  2026-10-05 10:00:00
```

```bash
curl 'localhost:8080/realty/3/readings?date_from=2026-10-05&date_to=2026-10-05'
# {"readings":[{"reading_date":"2026-10-05","user_id":3,"tariff_id":1,"gauge_id":3,"day_kw":16350,"night_kw":3244}],"count":1}
```

`DELETE FROM` убирает ошибочную строку и в ответе сервиса снова исходное показание.

## Структура репозитория

```
.
├── app/main.py         # HTTP-сервис
├── gen/generate.py     # генератор датасетов
├── scripts/load.sh     # загрузка CSV в ClickHouse
├── sql/schema.sql      # создание таблиц
├── sql/teardown.sql    # удаление таблиц
├── api/openapi.json    # схема API
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── .env.local
```
