#!/usr/bin/env bash
set -euo pipefail

set -a
source .env.local
set +a

url="http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/"
tables="dim_realty dim_gauges dim_tariffs dim_users fact_gauge_bindings fact_meter_readings fact_invoice"

ch() {
    curl -sS --fail-with-body \
        -H "X-ClickHouse-User: $CLICKHOUSE_USER" \
        -H "X-ClickHouse-Key: $CLICKHOUSE_PASSWORD" \
        "$@"
}

for t in $tables; do
    ch "$url" --data-binary "TRUNCATE TABLE $CLICKHOUSE_DATABASE.$t"
    ch "$url?query=INSERT+INTO+$CLICKHOUSE_DATABASE.$t+FORMAT+CSVWithNames" --data-binary "@data/$t.csv"
    echo "$t loaded"
done