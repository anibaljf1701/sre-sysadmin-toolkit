#!/bin/sh
set -eu

: "${PROMETHEUS_TARGETS:?Set PROMETHEUS_TARGETS as a comma-separated host:port list}"
: "${ENVIRONMENT:?Set ENVIRONMENT}"

case "$ENVIRONMENT" in
  *[!A-Za-z0-9_.-]*|'')
    echo "ENVIRONMENT may contain only letters, numbers, dots, underscores, and hyphens" >&2
    exit 1
    ;;
esac

case "$PROMETHEUS_TARGETS" in
  ,*|*,|*,,*)
    echo "PROMETHEUS_TARGETS contains an empty target" >&2
    exit 1
    ;;
esac

set -f
old_ifs=$IFS
IFS=,
output=/tmp/prometheus-targets.json.tmp
printf '[{"targets":[' > "$output"
separator=
for target in $PROMETHEUS_TARGETS; do
  case "$target" in
    ''|*[!A-Za-z0-9.:-]*)
      echo "Invalid Prometheus target: $target" >&2
      exit 1
      ;;
  esac
  printf '%s"%s"' "$separator" "$target" >> "$output"
  separator=,
done
IFS=$old_ifs
printf '],"labels":{"environment":"%s"}}]\n' "$ENVIRONMENT" >> "$output"
mv "$output" /tmp/prometheus-targets.json

exec "${PROMETHEUS_BIN:-/bin/prometheus}" "$@"