# Сценарии SCD

Все сценарии выполнены на загруженных данных. SQL запускался так:

```bash
docker compose exec clickhouse clickhouse-client --password supadupapwd --query "..."
```

## Собственник сменил фамилию (SCD 1)

```bash
curl -X PATCH localhost:8080/users/1 -H 'Content-Type: application/json' -d '{"fio":"Петрова Анна Сергеевна"}'
curl localhost:8080/users/1
# {"id":1,"fio":"Петрова Анна Сергеевна","phone":"+79282235520","phone_prev":""}
```

```sql
SELECT fio, updated_at FROM energosbyt.dim_users FINAL WHERE id = 1
-- Петрова Анна Сергеевна  2026-11-14 10:28:53

SELECT fio, updated_at FROM energosbyt.dim_users WHERE id = 1 ORDER BY updated_at
-- Иванов Дмитрий Алексеевич  2023-10-15 12:00:00
-- Петрова Анна Сергеевна  2026-11-14 10:28:53

OPTIMIZE TABLE energosbyt.dim_users FINAL
SELECT fio FROM energosbyt.dim_users WHERE id = 1
-- Петрова Анна Сергеевна
```

Сервис вставляет новую строку с тем же `id` и свежим `updated_at`. С `FINAL` видна только она.
Без `FINAL` до слияния физически лежат обе строки, после `OPTIMIZE` старая фамилия исчезает из таблицы.

## Собственник сменил телефон дважды (SCD 3)

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

При смене телефона текущее значение переезжает в `phone_prev`. Хранится ровно одно предыдущее значение, первый телефон `+79282235520` потерян, это и есть SCD 3.

## Изменился тариф с 1 ноября (SCD 2)

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

## Пересчёт счёта за старый месяц (SCD 2)

Счёт объекта 1 за октябрь 2024, выставлен 1 ноября 2024 по версии 560/280:

```sql
SELECT day_kw, night_kw, price, deadline, created_at FROM energosbyt.fact_invoice WHERE realty_id = 1 AND deadline = '2024-11-10'
-- 110  171  109480  2024-11-10  2024-11-01 09:00:00
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
-- 109480  2024-11-01 09:00:00
-- 109480  2026-11-14 10:28:54

SELECT 110 * price_day_kwph + 171 * price_night_kwph FROM energosbyt.dim_tariffs FINAL WHERE valid_to = '2099-01-01 00:00:00'
-- 121210
```

Старый счёт не изменился. Пересчитанный счёт получил ту же сумму 109480, потому что цена взята из версии на дату счёта, а не из текущей версии, которая дала бы 121210.

## Корректировка показания (ReplacingMergeTree)

```bash
curl -X POST localhost:8080/realty/1/readings -H 'Content-Type: application/json' \
  -d '{"user_id":1,"gauge_id":1,"tariff_id":1,"reading_date":"2026-10-01","day_kw":9000,"night_kw":7100}'
curl 'localhost:8080/realty/1/readings?date_from=2026-10-01&date_to=2026-10-01'
# {"readings":[{"reading_date":"2026-10-01","user_id":1,"tariff_id":1,"gauge_id":1,"day_kw":9000,"night_kw":7100}],"count":1}
```

```sql
SELECT day_kw, night_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 1 AND reading_date = '2026-10-01' ORDER BY created_at
-- 7473  7038  2026-10-01 10:00:00
-- 9000  7100  2026-11-14 10:28:54

SELECT day_kw, night_kw, created_at FROM energosbyt.fact_meter_readings FINAL WHERE realty_id = 1 AND reading_date = '2026-10-01'
-- 9000  7100  2026-11-14 10:28:54
```

Старая строка остаётся в таблице, сервис читает с `FINAL` и отдаёт одно значение за дату, с последним `created_at`.

## Замена счётчика (VersionedCollapsingMergeTree)

```bash
curl -X POST localhost:8080/realty/1/gauges -H 'Content-Type: application/json' -d '{"gauge_id":2}'
```

```sql
SELECT gauge_id, sign, version, created_at FROM energosbyt.fact_gauge_bindings WHERE realty_id = 1 ORDER BY version, sign DESC
-- 1   1  1  2023-10-15 12:00:00
-- 1  -1  1  2026-11-14 10:28:55
-- 2   1  2  2026-11-14 10:28:55

SELECT gauge_id, sign, version FROM energosbyt.fact_gauge_bindings FINAL WHERE realty_id = 1
-- 2  1  2
```

Сервис вставил строку аннулирования с `sign = -1` и тем же `version = 1`, что у активной установки, и новую установку с `version = 2`.
После `FINAL` пара схлопнулась, активной осталась только установка счётчика 2.

## Ошибочная строка с лишним нулём (DELETE)

Показание 77380 вместо 7738 для объекта 3 за 2026-10-05:

```sql
SELECT day_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05' ORDER BY created_at
-- 7738  2026-10-05 10:00:00
-- 77380  2026-11-14 10:28:55

DELETE FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05' AND day_kw = 77380

SELECT day_kw, created_at FROM energosbyt.fact_meter_readings WHERE realty_id = 3 AND reading_date = '2026-10-05'
-- 7738  2026-10-05 10:00:00
```

```bash
curl 'localhost:8080/realty/3/readings?date_from=2026-10-05&date_to=2026-10-05'
# {"readings":[{"reading_date":"2026-10-05","user_id":3,"tariff_id":1,"gauge_id":3,"day_kw":7738,"night_kw":3006}],"count":1}
```

`DELETE FROM` убирает ошибочную строку и в ответе сервиса снова исходное показание.
