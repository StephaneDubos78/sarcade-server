#!/bin/sh
set -e
pip install -q httpx
exec python "$@"
