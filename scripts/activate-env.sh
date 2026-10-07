#!/bin/bash
# Loads .env (if present) into every pixi task's environment.
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
