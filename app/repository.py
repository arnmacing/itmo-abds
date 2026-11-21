from app.db import insert, one, rows


def exists(table, key):
    """Есть ли в таблице строка с таким id."""
    return one(f"SELECT 1 FROM {table} WHERE id = {{id:UInt64}}", id=key)


def find_user(user_id):
    """Актуальная версия собственника."""
    return one(
        "SELECT id, fio, phone, phone_prev, created_at FROM dim_users FINAL WHERE id = {id:UInt64}",
        id=user_id,
    )


def save_user(user):
    """Новая версия собственника, старую схлопнет ReplacingMergeTree."""
    insert("dim_users", [list(user.values())], list(user))


def find_realty(realty_id):
    """Объект недвижимости."""
    return one(
        "SELECT id, address, square, type, number, rooms, floor, porch FROM dim_realty WHERE id = {id:UInt64}",
        id=realty_id,
    )


def add_reading(realty_id, reading):
    """Новая строка показания, корректировка за ту же дату тоже вставка."""
    insert(
        "fact_meter_readings",
        [[realty_id, *reading.values()]],
        ["realty_id", *reading],
    )


def find_readings(realty_id, date_from, date_to):
    """Показания за период, по одному актуальному на дату."""
    return rows(
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


def find_invoices(realty_id, limit, offset):
    """Страница счетов объекта, новые сверху."""
    return rows(
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


def count_invoices(realty_id):
    """Сколько всего счетов у объекта."""
    total = one(
        "SELECT count() AS n FROM fact_invoice WHERE realty_id = {id:UInt64}",
        id=realty_id,
    )
    return total["n"]


def find_tariff(day):
    """Версия тарифа, действовавшая на дату."""
    return one(
        """
        SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to
        FROM dim_tariffs FINAL
        WHERE valid_from <= {day:Date} AND {day:Date} < valid_to
        """,
        day=day,
    )


def find_active_binding(realty_id):
    """Активная установка счётчика на объекте."""
    return one(
        "SELECT gauge_id, version FROM fact_gauge_bindings FINAL WHERE realty_id = {id:UInt64} ORDER BY version DESC LIMIT 1",
        id=realty_id,
    )


def add_bindings(bindings):
    """Строки установки и аннулирования счётчиков."""
    insert(
        "fact_gauge_bindings", bindings, ["gauge_id", "realty_id", "sign", "version"]
    )
