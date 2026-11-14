import os
from datetime import date, datetime

import clickhouse_connect
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

app = FastAPI()
ENCODERS_BY_TYPE[datetime] = str
db = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ["CLICKHOUSE_HTTP_PORT"]),
    username=os.environ["CLICKHOUSE_USER"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
    database=os.environ["CLICKHOUSE_DATABASE"],
)

not_found = HTTPException(404, "Not found")


@app.exception_handler(RequestValidationError)
def invalid(_, exc):
    """Ошибка валидации: 400 с именем поля или параметра."""
    loc = exc.errors()[0]["loc"]
    kind = "field" if loc[0] == "body" else "parameter"
    name = loc[-1] if isinstance(loc[-1], str) else "body"
    return JSONResponse({"message": f'invalid "{name}" {kind}'}, 400)


@app.exception_handler(HTTPException)
def http_error(_, exc):
    """Ответ на HTTPException в формате {"message": ...}."""
    return JSONResponse({"message": exc.detail}, exc.status_code)


def one(sql, **params):
    """Первая строка результата запроса или None."""
    return next(db.query(sql, params).named_results(), None)


def rows(sql, **params):
    """Все строки результата запроса."""
    return list(db.query(sql, params).named_results())


def exists(table, key):
    """Есть ли в таблице строка с таким id."""
    return one(f"SELECT 1 FROM {table} WHERE id = {{id:UInt64}}", id=key)


@app.get("/ping")
def ping():
    """Проверка доступности."""
    return Response()


@app.get("/users/{user_id}")
def get_user(user_id: int):
    """Собственник по id."""
    user = one(
        "SELECT id, fio, phone, phone_prev FROM dim_users FINAL WHERE id = {id:UInt64}",
        id=user_id,
    )
    if not user:
        raise not_found
    return user


class UserPatch(BaseModel):
    fio: str | None = Field(None, min_length=1)
    phone: str | None = Field(None, min_length=1)


@app.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch):
    """Меняет ФИО (SCD 1) и телефон с сохранением предыдущего (SCD 3)."""
    if body.fio is None and body.phone is None:
        return JSONResponse({"message": 'invalid "fio" field'}, 400)
    user = one(
        "SELECT fio, phone, phone_prev, created_at FROM dim_users FINAL WHERE id = {id:UInt64}",
        id=user_id,
    )
    if not user:
        raise not_found
    if body.fio:
        user["fio"] = body.fio
    if body.phone and body.phone != user["phone"]:
        user["phone_prev"] = user["phone"]
        user["phone"] = body.phone
    db.insert("dim_users", [[user_id, *user.values()]], ["id", *user])
    return Response(status_code=204)


@app.get("/realty/{realty_id}")
def get_realty(realty_id: int):
    """Объект недвижимости по id."""
    realty = one(
        "SELECT id, address, square, type, number, rooms, floor, porch FROM dim_realty WHERE id = {id:UInt64}",
        id=realty_id,
    )
    if not realty:
        raise not_found
    return realty


class Reading(BaseModel):
    user_id: int
    gauge_id: int
    tariff_id: int
    reading_date: date
    day_kw: int = Field(ge=0)
    night_kw: int = Field(ge=0)


@app.post("/realty/{realty_id}/readings")
def post_reading(realty_id: int, body: Reading):
    """Сохраняет показание, повтор за ту же дату становится корректировкой."""
    if not (
        exists("dim_realty", realty_id)
        and exists("dim_users", body.user_id)
        and exists("dim_gauges", body.gauge_id)
        and exists("dim_tariffs", body.tariff_id)
    ):
        raise not_found
    reading = body.model_dump()
    db.insert(
        "fact_meter_readings", [[realty_id, *reading.values()]], ["realty_id", *reading]
    )
    return Response(status_code=201)


@app.get("/realty/{realty_id}/readings")
def get_readings(realty_id: int, date_from: date, date_to: date):
    """Актуальные показания объекта за период, по одному на дату."""
    if date_from > date_to:
        return JSONResponse({"message": 'invalid "date_from" parameter'}, 400)
    if not exists("dim_realty", realty_id):
        raise not_found
    readings = rows(
        """
        SELECT reading_date, user_id, tariff_id, gauge_id, day_kw, night_kw
        FROM fact_meter_readings FINAL
        WHERE realty_id = {id:UInt64} AND reading_date BETWEEN {date_from:Date} AND {date_to:Date}
        ORDER BY reading_date
        """,
        id=realty_id,
        date_from=date_from,
        date_to=date_to,
    )
    return {"readings": readings, "count": len(readings)}


@app.get("/realty/{realty_id}/invoices")
def get_invoices(
    realty_id: int, limit: int = Query(10, ge=0), offset: int = Query(0, ge=0)
):
    """Счета объекта, новые сверху, count без учёта пагинации."""
    if not exists("dim_realty", realty_id):
        raise not_found
    invoices = rows(
        """
        SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at
        FROM fact_invoice
        WHERE realty_id = {id:UInt64}
        ORDER BY created_at DESC
        LIMIT {limit:UInt64} OFFSET {offset:UInt64}
        """,
        id=realty_id,
        limit=limit,
        offset=offset,
    )
    total = one(
        "SELECT count() AS n FROM fact_invoice WHERE realty_id = {id:UInt64}",
        id=realty_id,
    )
    return {"invoices": invoices, "count": total["n"]}


@app.get("/tariffs")
def get_tariff(date: date):
    """Версия тарифа, действовавшая на дату."""
    tariff = one(
        """
        SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to
        FROM dim_tariffs FINAL
        WHERE valid_from <= {date:Date} AND {date:Date} < valid_to
        """,
        date=date,
    )
    if not tariff:
        raise not_found
    return tariff


class Gauge(BaseModel):
    gauge_id: int = Field(ge=1)


@app.post("/realty/{realty_id}/gauges")
def post_gauge(realty_id: int, body: Gauge):
    """Аннулирует активную установку и ставит новый счётчик."""
    if not (exists("dim_realty", realty_id) and exists("dim_gauges", body.gauge_id)):
        raise not_found
    active = one(
        "SELECT gauge_id, version FROM fact_gauge_bindings FINAL WHERE realty_id = {id:UInt64} ORDER BY version DESC LIMIT 1",
        id=realty_id,
    )
    bindings, version = [], 0
    if active:
        bindings.append([active["gauge_id"], realty_id, -1, active["version"]])
        version = active["version"]
    bindings.append([body.gauge_id, realty_id, 1, version + 1])
    db.insert(
        "fact_gauge_bindings", bindings, ["gauge_id", "realty_id", "sign", "version"]
    )
    return Response(status_code=201)
