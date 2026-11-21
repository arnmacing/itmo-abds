from app import repository


class NotFound(Exception):
    pass


def get_user(user_id):
    """Собственник без служебных полей."""
    user = repository.find_user(user_id)
    if not user:
        raise NotFound
    del user["created_at"]
    return user


def update_user(user_id, fio, phone):
    """ФИО перезаписывается (SCD 1), прежний телефон уходит в phone_prev (SCD 3)."""
    user = repository.find_user(user_id)
    if not user:
        raise NotFound
    if fio:
        user["fio"] = fio
    if phone and phone != user["phone"]:
        user["phone_prev"] = user["phone"]
        user["phone"] = phone
    repository.save_user(user)


def get_realty(realty_id):
    """Объект недвижимости."""
    realty = repository.find_realty(realty_id)
    if not realty:
        raise NotFound
    return realty


def add_reading(realty_id, reading):
    """Сохраняет показание, если объект, собственник, счётчик и тариф существуют."""
    if not (
        repository.exists("dim_realty", realty_id)
        and repository.exists("dim_users", reading.user_id)
        and repository.exists("dim_gauges", reading.gauge_id)
        and repository.exists("dim_tariffs", reading.tariff_id)
    ):
        raise NotFound
    repository.add_reading(realty_id, reading.model_dump())


def get_readings(realty_id, date_from, date_to):
    """Показания объекта за период."""
    if not repository.exists("dim_realty", realty_id):
        raise NotFound
    return repository.find_readings(realty_id, date_from, date_to)


def get_invoices(realty_id, limit, offset):
    """Страница счетов и общее их количество."""
    if not repository.exists("dim_realty", realty_id):
        raise NotFound
    invoices = repository.find_invoices(realty_id, limit, offset)
    return invoices, repository.count_invoices(realty_id)


def get_tariff(day):
    """Версия тарифа на дату."""
    tariff = repository.find_tariff(day)
    if not tariff:
        raise NotFound
    return tariff


def install_gauge(realty_id, gauge_id):
    """Аннулирует активную установку тем же version и ставит счётчик с version + 1."""
    if not (
        repository.exists("dim_realty", realty_id)
        and repository.exists("dim_gauges", gauge_id)
    ):
        raise NotFound
    active = repository.find_active_binding(realty_id)
    bindings, version = [], 0
    if active:
        bindings.append([active["gauge_id"], realty_id, -1, active["version"]])
        version = active["version"]
    bindings.append([gauge_id, realty_id, 1, version + 1])
    repository.add_bindings(bindings)
