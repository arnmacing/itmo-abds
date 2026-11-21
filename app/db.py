import os

import clickhouse_connect

client = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ["CLICKHOUSE_HTTP_PORT"]),
    username=os.environ["CLICKHOUSE_USER"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
    database=os.environ["CLICKHOUSE_DATABASE"],
)


def one(sql, **params):
    """Первая строка результата запроса или None."""
    return next(client.query(sql, params).named_results(), None)


def rows(sql, **params):
    """Все строки результата запроса."""
    return list(client.query(sql, params).named_results())


def insert(table, data, columns):
    """Вставляет строки в таблицу."""
    client.insert(table, data, columns)
