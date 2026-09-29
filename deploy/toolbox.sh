#!/bin/sh
# Work at conventional project paths inside the container; only manifests are
# copied back. Source directories are mounted individually by Compose.
set -eu
kind="$1"
shift
case "$kind" in
  python) cd /app; manifests="pyproject.toml uv.lock" ;;
  node) cd /app/web; manifests="package.json package-lock.json" ;;
  *) echo "Unknown toolbox: $kind" >&2; exit 2 ;;
esac
baseline=$(mktemp -d /tmp/science-agent-manifests.XXXXXX)
trap 'rm -rf "$baseline"' EXIT
if [ -d /manifests ]; then
  for file in $manifests; do
    cp "/manifests/$file" "$baseline/$file"
    cp "$baseline/$file" "$file"
  done
fi
"$@" &
child=$!
trap 'kill -TERM "$child" 2>/dev/null || true' TERM INT
status=0
wait "$child" || status=$?
if [ "$status" -eq 0 ] && [ -d /manifests ]; then
  # Read-only commands must never restore stale inputs over a concurrent update.
  # Check both files before writing either member of the manifest/lock pair.
  for file in $manifests; do
    if ! cmp -s "$file" "$baseline/$file" && ! cmp -s "/manifests/$file" "$baseline/$file"; then
      echo "Manifest changed concurrently; rerun this command: $file" >&2
      exit 1
    fi
  done
  for file in $manifests; do
    if ! cmp -s "$file" "$baseline/$file"; then
      cp "$file" "/manifests/$file.tmp"
      mv "/manifests/$file.tmp" "/manifests/$file"
    fi
  done
fi
exit "$status"
