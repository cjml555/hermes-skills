#!/usr/bin/env bash
# List X11 top-level windows, optionally filtered by name substring.
# Usage: ./window-check.sh [name-substring]
# Works on X11 only; under Wayland use a compositor-specific tool instead.

set -uo pipefail

needle="${1:-}"

ids=$(xprop -root _NET_CLIENT_LIST 2>/dev/null | sed 's/.*# //' | tr ',' '\n')

found=0
for id in $ids; do
  [ -z "$id" ] && continue
  name=$(xprop -id "$id" WM_NAME 2>/dev/null | sed 's/.*= //; s/^"\(.*\)"$/\1/')
  [ -z "$name" ] && continue
  if [ -z "$needle" ] || printf '%s' "$name" | grep -qi -- "$needle"; then
    printf '%s  %s\n' "$id" "$name"
    found=1
  fi
done

[ "$found" -eq 0 ] && echo "no matching window (needle='${needle}')" && exit 1
exit 0
