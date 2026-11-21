from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from app import services
from app.models import Gauge, Reading, UserPatch

router = APIRouter()


def bad_request(message):
    return JSONResponse({"message": message}, 400)


@router.get("/ping")
def ping():
    """Проверка доступности."""
    return Response()


@router.get("/users/{user_id}")
def get_user(user_id: int):
    """Собственник по id."""
    return services.get_user(user_id)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch):
    """Меняет ФИО (SCD 1) и телефон с сохранением предыдущего (SCD 3)."""
    if body.fio is None and body.phone is None:
        return bad_request('invalid "fio" field')
    services.update_user(user_id, body.fio, body.phone)
    return Response(status_code=204)


@router.get("/realty/{realty_id}")
def get_realty(realty_id: int):
    """Объект недвижимости по id."""
    return services.get_realty(realty_id)


@router.post("/realty/{realty_id}/readings")
def post_reading(realty_id: int, body: Reading):
    """Сохраняет показание, повтор за ту же дату становится корректировкой."""
    services.add_reading(realty_id, body)
    return Response(status_code=201)


@router.get("/realty/{realty_id}/readings")
def get_readings(realty_id: int, date_from: date, date_to: date):
    """Актуальные показания объекта за период, по одному на дату."""
    if date_from > date_to:
        return bad_request('invalid "date_from" parameter')
    readings = services.get_readings(realty_id, date_from, date_to)
    return {"readings": readings, "count": len(readings)}


@router.get("/realty/{realty_id}/invoices")
def get_invoices(
    realty_id: int, limit: int = Query(10, ge=0), offset: int = Query(0, ge=0)
):
    """Счета объекта, новые сверху, count без учёта пагинации."""
    invoices, total = services.get_invoices(realty_id, limit, offset)
    return {"invoices": invoices, "count": total}


@router.get("/tariffs")
def get_tariff(date: date):
    """Версия тарифа, действовавшая на дату."""
    return services.get_tariff(date)


@router.post("/realty/{realty_id}/gauges")
def post_gauge(realty_id: int, body: Gauge):
    """Аннулирует активную установку и ставит новый счётчик."""
    services.install_gauge(realty_id, body.gauge_id)
    return Response(status_code=201)
