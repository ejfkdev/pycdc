#!/usr/bin/env bash
# Fetch the real-world corpus used by the README performance section.
#
# For each project below: resolve the LATEST RELEASE TAG (not the default
# branch), sparse-checkout exactly one source directory at that tag, and
# copy it into tests/realworld/<name>/. Everything is then compiled to
# .pyc with the interpreter given by $PYC_PYTHON (default: the 3.12 from
# uv, falling back to python3).
#
# tests/realworld/ is git-ignored: this script is the way to recreate it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/tests/realworld"
PY="${PYC_PYTHON:-$HOME/.local/share/uv/python/cpython-3.12.14-macos-aarch64-none/bin/python3.12}"
[ -x "$PY" ] || PY=python3

# repo<TAB>path-in-repo<TAB>dest-name
PROJECTS=(
  "yt-dlp/yt-dlp|yt_dlp|yt_dlp"
  "matplotlib/matplotlib|lib/matplotlib|matplotlib"
  "pandas-dev/pandas|pandas|pandas"
  "django/django|django|django"
  "sympy/sympy|sympy|sympy"
  "scikit-learn/scikit-learn|sklearn|sklearn"
  "ansible/ansible|lib/ansible|ansible"
)

mkdir -p "$DEST"
manifest="$DEST/manifest.tsv"
: > "$manifest"

for entry in "${PROJECTS[@]}"; do
  repo="${entry%%|*}"; rest="${entry#*|}"
  path="${rest%%|*}"; name="${rest##*|}"
  # latest release tag; some repos (django) mark no release as "latest",
  # so fall back to the tags API and, failing that, to a version sort of
  # ls-remote output
  tag="$(gh api "repos/$repo/releases/latest" --jq .tag_name 2>/dev/null || true)"
  case "$tag" in
    ""|*"Not Found"*|*"message"*)
      # prefer plain version tags (django publishes branch-style tags too)
      tag="$(gh api "repos/$repo/tags" --paginate --jq '.[].name' 2>/dev/null \
             | grep -E '^v?[0-9]+\.[0-9]+(\.[0-9]+)?$' | sort -V | tail -1 || true)"
      [ -n "$tag" ] || tag="$(gh api "repos/$repo/tags" --jq '.[0].name' 2>/dev/null || true)" ;;
  esac
  case "$tag" in
    ""|*"Not Found"*|*"message"*)
      tag="$(git -c http.version=HTTP/1.1 ls-remote --tags --refs "https://github.com/$repo" \
             | awk -F/ '{print $NF}' | grep -Ev 'rc|a[0-9]+$|b[0-9]+$' | sort -V | tail -1)" ;;
  esac
  if [ -z "$tag" ]; then
    echo "!! $repo: no release tag found, skipping" >&2
    continue
  fi
  echo "   tag: $tag"
  echo "== $repo @ $tag  ($path)"
  tmp="$(mktemp -d)"
  git -c http.version=HTTP/1.1 clone --depth 1 --branch "$tag" \
      --filter=blob:none --sparse "https://github.com/$repo" "$tmp" >/dev/null 2>&1
  git -C "$tmp" -c http.version=HTTP/1.1 sparse-checkout set "$path" >/dev/null
  rm -rf "$DEST/$name"
  cp -R "$tmp/$path" "$DEST/$name"
  rm -rf "$tmp"
  printf '%s\t%s\t%s\n' "$name" "$repo" "$tag" >> "$manifest"
done

echo "== compiling to .pyc with $($PY -V 2>&1)"
"$PY" -m compileall -q -b "$DEST" 2>/dev/null || true

n_py=$(find "$DEST" -name '*.py' | wc -l | tr -d ' ')
n_pyc=$(find "$DEST" -name '*.pyc' | wc -l | tr -d ' ')
echo "== $n_py .py -> $n_pyc .pyc"
cat "$manifest"