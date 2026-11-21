CREATE DATABASE IF NOT EXISTS energosbyt;

-- Объекты недвижимости
CREATE TABLE IF NOT EXISTS energosbyt.dim_realty
(
    id          UInt64   COMMENT 'Идентификатор объекта',
    address     String   COMMENT 'Адрес дома',
    square      UInt32   COMMENT 'Площадь, м²',
    type        String   COMMENT 'flat - квартира, nrcp - нежилое помещение',
    number      String   COMMENT 'Номер квартиры (для нежилых помещений пусто)',
    rooms       UInt8    COMMENT 'Количество комнат',
    floor       UInt8    COMMENT 'Этаж',
    porch       UInt8    COMMENT 'Подъезд',
    created_at  DateTime DEFAULT now() COMMENT 'Дата создания записи'
)
ENGINE = MergeTree
ORDER BY id;

-- Счётчики
CREATE TABLE IF NOT EXISTS energosbyt.dim_gauges
(
    id          UInt64   COMMENT 'Идентификатор счётчика',
    name        String   COMMENT 'Модель счётчика',
    country     String   COMMENT 'Страна производства',
    created_at  DateTime DEFAULT now() COMMENT 'Дата создания записи'
)
ENGINE = MergeTree
ORDER BY id;

-- Тарифы
CREATE TABLE IF NOT EXISTS energosbyt.dim_tariffs
(
    id                UInt64   COMMENT 'Идентификатор тарифа',
    name              String   COMMENT 'Название тарифа',
    price_day_kwph    UInt32   COMMENT 'Цена кВт/ч в дневное время, копейки',
    price_night_kwph  UInt32   COMMENT 'Цена кВт/ч в ночное время, копейки',
    valid_from        DateTime COMMENT 'Начало действия версии тарифа',
    valid_to          DateTime DEFAULT toDateTime('2099-01-01 00:00:00') COMMENT 'Конец действия версии (2099-01-01 00:00:00 у открытой)',
    created_at        DateTime DEFAULT now() COMMENT 'Дата создания записи',
    updated_at        DateTime DEFAULT now() COMMENT 'Версия строки для ReplacingMergeTree'
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (id, valid_from);

-- Собственники
CREATE TABLE IF NOT EXISTS energosbyt.dim_users
(
    id          UInt64   COMMENT 'Идентификатор собственника',
    fio         String   COMMENT 'ФИО (SCD 1: перезаписывается)',
    phone       String   COMMENT 'Текущий телефон (SCD 3)',
    phone_prev  String   DEFAULT '' COMMENT 'Предыдущий телефон, пусто если его не было (SCD 3)',
    created_at  DateTime DEFAULT now() COMMENT 'Дата создания записи',
    updated_at  DateTime DEFAULT now() COMMENT 'Версия строки для ReplacingMergeTree'
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Установка счётчика на объект
CREATE TABLE IF NOT EXISTS energosbyt.fact_gauge_bindings
(
    gauge_id    UInt64   COMMENT 'Идентификатор счётчика',
    realty_id   UInt64   COMMENT 'Идентификатор объекта',
    created_at  DateTime DEFAULT now() COMMENT 'Дата создания записи',
    sign        Int8     COMMENT '1 - установка, -1 - аннулирование',
    version     UInt64   COMMENT 'Версия привязки'
)
ENGINE = VersionedCollapsingMergeTree(sign, version)
ORDER BY (realty_id, gauge_id, version);

-- Показания счётчиков по дням
CREATE TABLE IF NOT EXISTS energosbyt.fact_meter_readings
(
    realty_id     UInt64   COMMENT 'Идентификатор объекта',
    user_id       UInt64   COMMENT 'Идентификатор собственника',
    tariff_id     UInt64   COMMENT 'Идентификатор тарифа, по которому считается счёт',
    gauge_id      UInt64   COMMENT 'Идентификатор счётчика',
    reading_date  Date     COMMENT 'Дата показания',
    day_kw        UInt32   COMMENT 'Показание дневного счётчика, кВт/ч',
    night_kw      UInt32   COMMENT 'Показание ночного счётчика, кВт/ч',
    created_at    DateTime DEFAULT now() COMMENT 'Время передачи показания, побеждает последняя запись'
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(reading_date)
ORDER BY (realty_id, reading_date);

-- Счета
CREATE TABLE IF NOT EXISTS energosbyt.fact_invoice
(
    realty_id   UInt64   COMMENT 'Идентификатор объекта',
    user_id     UInt64   COMMENT 'Идентификатор собственника',
    tariff_id   UInt64   COMMENT 'Идентификатор тарифа',
    gauge_id    UInt64   COMMENT 'Идентификатор счётчика',
    day_kw      UInt32   COMMENT 'Потреблённые кВт/ч дневного тарифа',
    night_kw    UInt32   COMMENT 'Потреблённые кВт/ч ночного тарифа',
    price       UInt64   COMMENT 'Сумма счёта, копейки',
    deadline    Date     COMMENT 'Срок оплаты',
    created_at  DateTime DEFAULT now() COMMENT 'Дата выставления счёта'
)
ENGINE = MergeTree
PARTITION BY toYear(created_at)
ORDER BY (realty_id, created_at);
