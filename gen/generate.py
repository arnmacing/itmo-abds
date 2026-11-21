import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path("data")
SEED = 42
REALTY_COUNT = 1000
PERIOD_FROM = date(2023, 11, 1)
PERIOD_TO = date(2026, 10, 31)
CORRECTION_SHARE = 0.03
GAUGE_REPLACE_SHARE = 0.05
CREATED_AT = "2023-10-15 12:00:00"
OPEN_VALID_TO = "2099-01-01 00:00:00"

HOUSES = [
    "г. Санкт-Петербург, Кронверкский пр., д. 49",
    "г. Санкт-Петербург, ул. Ломоносова, д. 9",
    "г. Санкт-Петербург, Биржевая линия, д. 14",
    "г. Санкт-Петербург, ул. Чайковского, д. 11",
    "г. Санкт-Петербург, пер. Гривцова, д. 14",
]
GAUGE_MODELS = [
    ("Меркурий 206", "Россия"),
    ("Нева МТ 124", "Россия"),
    ("Энергомера CE102", "Россия"),
    ("Landis+Gyr E650", "Швейцария"),
    ("Iskra ME162", "Словения"),
    ("Elster A1140", "Германия"),
]
LAST_NAMES = ["Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Волков"]
FIRST_NAMES = ["Иван", "Пётр", "Алексей", "Дмитрий", "Сергей", "Андрей", "Михаил"]
PATRONYMICS = ["Иванович", "Петрович", "Алексеевич", "Дмитриевич", "Сергеевич"]

TARIFFS = [
    # id, name, price_day, price_night, valid_from, valid_to
    (1, "День–Ночь", 560, 280, "2023-11-01 00:00:00", "2024-11-01 00:00:00"),
    (1, "День–Ночь", 600, 300, "2024-11-01 00:00:00", "2025-11-01 00:00:00"),
    (1, "День–Ночь", 620, 310, "2025-11-01 00:00:00", OPEN_VALID_TO),
]

rng = random.Random(SEED)


def write_csv(name, header, rows):
    """Пишет CSV с заголовком в папку OUT."""
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def phone():
    """Случайный номер телефона."""
    return "+79" + "".join(rng.choices("0123456789", k=9))


def tariff_for(month):
    """Версия тарифа, действующая в первый день месяца."""
    ts = f"{month} 00:00:00"
    for t in TARIFFS:
        if t[4] <= ts < t[5]:
            return t


def main():
    """Генерирует все датасеты."""
    OUT.mkdir(exist_ok=True)

    # dim_realty
    realty = []
    for rid in range(1, REALTY_COUNT + 1):
        house = HOUSES[(rid - 1) * len(HOUSES) // REALTY_COUNT]
        if rng.random() < 0.9:
            rooms = rng.randint(1, 4)
            square = 28 + rooms * rng.randint(12, 22)
            floor, porch = rng.randint(1, 16), rng.randint(1, 4)
            realty.append(
                (rid, house, square, "flat", rid, rooms, floor, porch, CREATED_AT)
            )
        else:
            square = rng.randint(40, 300)
            porch = rng.randint(1, 4)
            realty.append((rid, house, square, "nrcp", "", 0, 1, porch, CREATED_AT))
    write_csv(
        "dim_realty.csv",
        [
            "id",
            "address",
            "square",
            "type",
            "number",
            "rooms",
            "floor",
            "porch",
            "created_at",
        ],
        realty,
    )

    # dim_users
    users = []
    for uid in range(1, REALTY_COUNT + 1):
        fio = f"{rng.choice(LAST_NAMES)} {rng.choice(FIRST_NAMES)} {rng.choice(PATRONYMICS)}"
        prev = phone() if rng.random() < 0.1 else ""
        users.append((uid, fio, phone(), prev, CREATED_AT, CREATED_AT))
    write_csv(
        "dim_users.csv",
        ["id", "fio", "phone", "phone_prev", "created_at", "updated_at"],
        users,
    )

    # dim_tariffs
    write_csv(
        "dim_tariffs.csv",
        [
            "id",
            "name",
            "price_day_kwph",
            "price_night_kwph",
            "valid_from",
            "valid_to",
            "created_at",
            "updated_at",
        ],
        [(*t, t[4], t[4]) for t in TARIFFS],
    )

    # dim_gauges + fact_gauge_bindings
    gauges, bindings = [], []
    replaced = {}  # realty_id -> (дата замены, новый gauge_id)
    for rid in range(1, REALTY_COUNT + 1):
        gauges.append((rid, *rng.choice(GAUGE_MODELS), CREATED_AT))
        bindings.append((rid, rid, CREATED_AT, 1, 1))
        if rng.random() < GAUGE_REPLACE_SHARE:
            gid = len(gauges) + 1
            day = PERIOD_FROM + timedelta(days=rng.randint(200, 1000))
            ts = f"{day} 09:00:00"
            gauges.append((gid, *rng.choice(GAUGE_MODELS), ts))
            bindings.append((rid, rid, ts, -1, 1))
            bindings.append((gid, rid, ts, 1, 2))
            replaced[rid] = (day, gid)
    write_csv("dim_gauges.csv", ["id", "name", "country", "created_at"], gauges)
    write_csv(
        "fact_gauge_bindings.csv",
        ["gauge_id", "realty_id", "created_at", "sign", "version"],
        bindings,
    )

    # fact_meter_readings + fact_invoice
    days = [
        PERIOD_FROM + timedelta(days=i)
        for i in range((PERIOD_TO - PERIOD_FROM).days + 1)
    ]
    months = sorted({d.replace(day=1) for d in days})
    day_month = [months.index(d.replace(day=1)) for d in days]
    invoices = []
    n_readings = 0
    with (OUT / "fact_meter_readings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "realty_id",
                "user_id",
                "tariff_id",
                "gauge_id",
                "reading_date",
                "day_kw",
                "night_kw",
                "created_at",
            ]
        )
        for rid in range(1, REALTY_COUNT + 1):
            gauge = rid
            day_kw, night_kw = rng.randint(0, 5000), rng.randint(0, 2000)
            base_day, base_night = rng.randint(3, 12), rng.randint(1, 5)
            used = [[0, 0] for _ in months]
            rows = []
            for i, d in enumerate(days):
                if rid in replaced and d == replaced[rid][0]:
                    gauge, day_kw, night_kw = replaced[rid][1], 0, 0
                dk, nk = base_day + rng.randint(-2, 4), base_night + rng.randint(-1, 2)
                day_kw += dk
                night_kw += nk
                used[day_month[i]][0] += dk
                used[day_month[i]][1] += nk
                rows.append((rid, rid, 1, gauge, d, day_kw, night_kw, f"{d} 10:00:00"))
                if rng.random() < CORRECTION_SHARE:
                    # корректировка: уточнили показание позже в тот же день
                    corr = rng.randint(1, 5)
                    day_kw += corr
                    used[day_month[i]][0] += corr
                    rows.append(
                        (rid, rid, 1, gauge, d, day_kw, night_kw, f"{d} 18:30:00")
                    )
            w.writerows(rows)
            n_readings += len(rows)

            for m, (dkw, nkw) in zip(months, used):
                t = tariff_for(m)
                nxt = (m + timedelta(days=32)).replace(day=1)
                gauge = (
                    replaced[rid][1]
                    if rid in replaced and replaced[rid][0] < nxt
                    else rid
                )
                price = dkw * t[2] + nkw * t[3]
                invoices.append(
                    (
                        rid,
                        rid,
                        t[0],
                        gauge,
                        dkw,
                        nkw,
                        price,
                        nxt.replace(day=10),
                        f"{nxt} 09:00:00",
                    )
                )
    write_csv(
        "fact_invoice.csv",
        [
            "realty_id",
            "user_id",
            "tariff_id",
            "gauge_id",
            "day_kw",
            "night_kw",
            "price",
            "deadline",
            "created_at",
        ],
        invoices,
    )

    print("dim_realty", len(realty))
    print("dim_gauges", len(gauges))
    print("dim_tariffs", len(TARIFFS))
    print("dim_users", len(users))
    print("fact_gauge_bindings", len(bindings))
    print("fact_meter_readings", n_readings)
    print("fact_invoice", len(invoices))


if __name__ == "__main__":
    main()
