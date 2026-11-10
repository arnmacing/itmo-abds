#!/usr/bin/env bash
set -e

source .env.local

url="http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/"
auth=(-H "X-ClickHouse-User: $CLICKHOUSE_USER" -H "X-ClickHouse-Key: $CLICKHOUSE_PASSWORD")
tables="dim_realty dim_gauges dim_tariffs dim_users fact_gauge_bindings fact_meter_readings fact_invoice"

for t in $tables; do
    curl -sS --fail-with-body "${auth[@]}" "$url" --data-binary "TRUNCATE TABLE $CLICKHOUSE_DATABASE.$t"
    curl -sS --fail-with-body "${auth[@]}" "$url?query=INSERT+INTO+$CLICKHOUSE_DATABASE.$t+FORMAT+CSVWithNames" --data-binary "@data/$t.csv"
    echo "$t loaded"
done
