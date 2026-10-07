#!/bin/bash
# Loads .env (if present) and path defaults into every pixi task's
# environment.
#
# pixi has no built-in .env support (only pixi.toml's own
# [activation.env] table), so this is the whole mechanism: plain bash,
# run once at environment activation, no extra Python dependency.
set -euo pipefail

if [ -f "$PIXI_PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PIXI_PROJECT_ROOT/.env"
    set +a
fi

# Defaults, applied only where neither the shell nor .env set a value.
# Absolute paths from the workspace root so the dlt pipeline, dbt, and
# the app all resolve the same files whatever directory a task runs in.
export FINANCE_DUCKDB_PATH="${FINANCE_DUCKDB_PATH:-$PIXI_PROJECT_ROOT/data/finance.duckdb}"
export FINANCE_STATEMENTS_ROOT="${FINANCE_STATEMENTS_ROOT:-$PIXI_PROJECT_ROOT/data/statements}"

# Privacy: nothing leaves this machine at runtime. dlt and dbt both send
# anonymous usage telemetry by default, and dbt Fusion also checks a CDN
# for new versions on every run. Off, unless the shell or .env opts in.
export RUNTIME__DLTHUB_TELEMETRY="${RUNTIME__DLTHUB_TELEMETRY:-false}"
export DO_NOT_TRACK="${DO_NOT_TRACK:-1}"
export DBT_SEND_ANONYMOUS_USAGE_STATS="${DBT_SEND_ANONYMOUS_USAGE_STATS:-false}"
export DBT_DISABLE_VERSION_CHECK="${DBT_DISABLE_VERSION_CHECK:-1}"
