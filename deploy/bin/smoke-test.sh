#!/usr/bin/env bash
set -Eeuo pipefail

die() {
    printf 'smoke-test: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 2 ]] || die "usage: ${0##*/} CANDIDATE_BASE_URL PUBLIC_BASE_URL"
CANDIDATE_BASE_URL="${1%/}"
PUBLIC_BASE_URL="${2%/}"
SMOKE_RAG_QUESTION="${SMOKE_RAG_QUESTION:-}"
SMOKE_WIKI_PAGE_ID="${SMOKE_WIKI_PAGE_ID:-}"
SMOKE_MEDIA_PUBLIC_BASE_URL="${SMOKE_MEDIA_PUBLIC_BASE_URL:-}"
[[ "$CANDIDATE_BASE_URL" =~ ^http://127\.0\.0\.1:[0-9]+$ ]] \
    || die "CANDIDATE_BASE_URL must be an explicit loopback HTTP origin"
[[ "$PUBLIC_BASE_URL" =~ ^https?://[^/]+$ ]] \
    || die "PUBLIC_BASE_URL must be an HTTP(S) origin"
[[ -n "$SMOKE_RAG_QUESTION" ]] \
    || die "SMOKE_RAG_QUESTION is required; all RAG checks are mandatory"
if [[ -n "$SMOKE_MEDIA_PUBLIC_BASE_URL" ]]; then
    [[ "$SMOKE_MEDIA_PUBLIC_BASE_URL" =~ ^https://[^/]+(/.*)?$ ]] \
        || die "SMOKE_MEDIA_PUBLIC_BASE_URL must be an HTTPS base"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT

fetch() {
    local url="$1"
    local output="$2"
    local timeout="${3:-20}"
    curl \
        --silent \
        --show-error \
        --fail \
        --connect-timeout 5 \
        --max-time "$timeout" \
        --output "$output" \
        "$url"
}

fetch "$CANDIDATE_BASE_URL/" "$TMP_DIR/index.html"
python3 - "$TMP_DIR/index.html" >"$TMP_DIR/asset-path" <<'PY'
import html.parser
import pathlib
import sys


class Assets(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.paths.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.paths.append(values["href"])


text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
if '<div id="root"></div>' not in text:
    raise SystemExit("smoke-test: candidate is not the formal React shell")
parser = Assets()
parser.feed(text)
paths = [path for path in parser.paths if path.startswith("/assets/") and ".." not in path]
if not paths:
    raise SystemExit("smoke-test: formal React shell has no built asset")
print(paths[0])
PY
ASSET_PATH="$(<"$TMP_DIR/asset-path")"
fetch "$CANDIDATE_BASE_URL$ASSET_PATH" "$TMP_DIR/formal-asset"
[[ -s "$TMP_DIR/formal-asset" ]] || die "formal React asset response is empty"

fetch "$CANDIDATE_BASE_URL/health" "$TMP_DIR/health.json"
python3 - "$TMP_DIR/health.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "status": "ok",
    "vectorstore_loaded": True,
    "provenance_status": "pass",
    "llm_ready": True,
}
if any(payload.get(key) != value for key, value in required.items()):
    raise SystemExit("smoke-test: candidate health is not fully ready")
PY

fetch "$CANDIDATE_BASE_URL/api/wiki/health" "$TMP_DIR/wiki-health.json"
python3 - "$TMP_DIR/wiki-health.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ready") is not True or int(payload.get("pageCount", 0)) < 1:
    raise SystemExit("smoke-test: Wiki health is not ready")
PY

fetch "$CANDIDATE_BASE_URL/api/wiki/pages?limit=1" "$TMP_DIR/wiki-list.json"
if [[ -z "$SMOKE_WIKI_PAGE_ID" ]]; then
    SMOKE_WIKI_PAGE_ID="$(
        python3 - "$TMP_DIR/wiki-list.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
items = payload.get("items")
if not isinstance(items, list) or not items or not items[0].get("pageId"):
    raise SystemExit("smoke-test: Wiki list contains no discoverable detail fixture")
print(items[0]["pageId"])
PY
    )"
fi
ENCODED_PAGE_ID="$(
    python3 - "$SMOKE_WIKI_PAGE_ID" <<'PY'
import sys
import urllib.parse

print(urllib.parse.quote(sys.argv[1], safe=""))
PY
)"
fetch \
    "$CANDIDATE_BASE_URL/api/wiki/pages/$ENCODED_PAGE_ID" \
    "$TMP_DIR/wiki-detail.json"
python3 - "$TMP_DIR/wiki-detail.json" "$SMOKE_WIKI_PAGE_ID" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("pageId") != sys.argv[2]:
    raise SystemExit("smoke-test: Wiki detail does not match the requested fixture")
PY

python3 - "$SMOKE_RAG_QUESTION" "$TMP_DIR/ask-request.json" <<'PY'
import json
import pathlib
import sys

pathlib.Path(sys.argv[2]).write_text(
    json.dumps({"question": sys.argv[1]}, ensure_ascii=False),
    encoding="utf-8",
)
PY
curl \
    --silent \
    --show-error \
    --fail \
    --connect-timeout 5 \
    --max-time 90 \
    --header 'Content-Type: application/json' \
    --data-binary "@$TMP_DIR/ask-request.json" \
    --output "$TMP_DIR/ask-response.json" \
    "$CANDIDATE_BASE_URL/api/ask"
MEDIA_URL="$(
    python3 \
        - "$TMP_DIR/ask-response.json" "$SMOKE_MEDIA_PUBLIC_BASE_URL" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
allowed_https_base = sys.argv[2].rstrip("/")
if not isinstance(payload.get("answer"), str) or not payload["answer"].strip():
    raise SystemExit("smoke-test: synchronous RAG response has no answer")


def urls(value):
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str):
            yield url
        for child in value.values():
            yield from urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from urls(child)


for candidate in urls(payload):
    if candidate.startswith("/media/"):
        print(candidate)
        break
    if allowed_https_base and (
        candidate == allowed_https_base
        or candidate.startswith(allowed_https_base + "/")
    ):
        print(candidate)
        break
else:
    raise SystemExit("smoke-test: RAG response has no projected public media URL")
PY
)"

curl \
    --silent \
    --show-error \
    --fail \
    --connect-timeout 5 \
    --max-time 90 \
    --header 'Content-Type: application/json' \
    --header 'Accept: text/event-stream' \
    --data-binary "@$TMP_DIR/ask-request.json" \
    --output "$TMP_DIR/ask-stream.txt" \
    "$CANDIDATE_BASE_URL/api/ask/stream"
grep -Eq '^event:[[:space:]]*done[[:space:]]*$' "$TMP_DIR/ask-stream.txt" \
    || die "RAG SSE response did not terminate with event: done"

if [[ "$MEDIA_URL" == /media/* ]]; then
    MEDIA_RETRIEVAL_URL="$PUBLIC_BASE_URL$MEDIA_URL"
else
    MEDIA_RETRIEVAL_URL="$MEDIA_URL"
fi
fetch "$MEDIA_RETRIEVAL_URL" "$TMP_DIR/media-object" 30
[[ -s "$TMP_DIR/media-object" ]] || die "projected media object is empty"

printf 'smoke tests passed\n'
