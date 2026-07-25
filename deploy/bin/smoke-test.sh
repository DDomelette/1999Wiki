#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_HELPER="${OPS_HELPER:-$SCRIPT_DIR/ops_helper.py}"

die() {
    printf 'smoke-test: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 3 ]] \
    || die "usage: ${0##*/} CANDIDATE_BASE_URL PUBLIC_BASE_URL APP_ENV_FILE"
CANDIDATE_BASE_URL="${1%/}"
PUBLIC_BASE_URL="${2%/}"
APP_ENV_FILE="$3"
SMOKE_RAG_QUESTION="${SMOKE_RAG_QUESTION:-}"
SMOKE_WIKI_PAGE_ID="${SMOKE_WIKI_PAGE_ID:-}"
[[ "$CANDIDATE_BASE_URL" =~ ^http://127\.0\.0\.1:[0-9]+$ ]] \
    || die "CANDIDATE_BASE_URL must be an explicit loopback HTTP origin"
[[ "$PUBLIC_BASE_URL" =~ ^https?://[^/]+$ ]] \
    || die "PUBLIC_BASE_URL must be an HTTP(S) origin"
[[ -n "$SMOKE_RAG_QUESTION" ]] \
    || die "SMOKE_RAG_QUESTION is required; all RAG checks are mandatory"
MEDIA_PUBLIC_BASE_URL="$(
    python3 "$OPS_HELPER" emit-media-base "$APP_ENV_FILE"
)" || die "APP_ENV_FILE is not valid"

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT

fetch() {
    local url="$1"
    local output="$2"
    local headers="$3"
    local timeout="${4:-20}"
    curl \
        --silent \
        --show-error \
        --fail \
        --location \
        --connect-timeout 5 \
        --max-time "$timeout" \
        --dump-header "$headers" \
        --output "$output" \
        --write-out '%{http_code}\n%{content_type}\n' \
        "$url"
}

assert_non_html_response() {
    local metadata_file="$1"
    local body_file="$2"
    local label="$3"
    python3 - "$metadata_file" "$body_file" "$label" <<'PY'
import pathlib
import sys

metadata = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
if len(metadata) != 2 or not metadata[0].startswith("2"):
    raise SystemExit(f"smoke-test: {sys.argv[3]} did not end in HTTP 2xx")
content_type = metadata[1].lower()
body = pathlib.Path(sys.argv[2]).read_bytes()
prefix = body[:1024].lstrip().lower()
if not body:
    raise SystemExit(f"smoke-test: {sys.argv[3]} response is empty")
if "text/html" in content_type or prefix.startswith((b"<!doctype html", b"<html")):
    raise SystemExit(f"smoke-test: {sys.argv[3]} resolved to an HTML fallback")
PY
}

fetch \
    "$CANDIDATE_BASE_URL/" \
    "$TMP_DIR/index.html" \
    "$TMP_DIR/index.headers" \
    >"$TMP_DIR/index.metadata"
python3 - "$TMP_DIR/index.html" >"$TMP_DIR/asset-path" <<'PY'
import html.parser
import pathlib
import re
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
hashed = re.compile(r"^/assets/[^/?#]+-[A-Za-z0-9_-]{6,}\.(?:css|js)$")
paths = [path for path in parser.paths if hashed.fullmatch(path)]
if not paths:
    raise SystemExit("smoke-test: formal React shell has no hashed built asset")
print(paths[0])
PY
ASSET_PATH="$(<"$TMP_DIR/asset-path")"
fetch \
    "$CANDIDATE_BASE_URL$ASSET_PATH" \
    "$TMP_DIR/formal-asset" \
    "$TMP_DIR/formal-asset.headers" \
    >"$TMP_DIR/formal-asset.metadata"
assert_non_html_response \
    "$TMP_DIR/formal-asset.metadata" \
    "$TMP_DIR/formal-asset" \
    "formal React asset"

fetch \
    "$CANDIDATE_BASE_URL/health" \
    "$TMP_DIR/health.json" \
    "$TMP_DIR/health.headers" \
    >"$TMP_DIR/health.metadata"
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

fetch \
    "$CANDIDATE_BASE_URL/api/wiki/health" \
    "$TMP_DIR/wiki-health.json" \
    "$TMP_DIR/wiki-health.headers" \
    >"$TMP_DIR/wiki-health.metadata"
python3 - "$TMP_DIR/wiki-health.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ready") is not True or int(payload.get("pageCount", 0)) < 1:
    raise SystemExit("smoke-test: Wiki health is not ready")
PY

fetch \
    "$CANDIDATE_BASE_URL/api/wiki/pages?limit=1" \
    "$TMP_DIR/wiki-list.json" \
    "$TMP_DIR/wiki-list.headers" \
    >"$TMP_DIR/wiki-list.metadata"
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
    "$TMP_DIR/wiki-detail.json" \
    "$TMP_DIR/wiki-detail.headers" \
    >"$TMP_DIR/wiki-detail.metadata"
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
    --location \
    --connect-timeout 5 \
    --max-time 90 \
    --header 'Content-Type: application/json' \
    --data-binary "@$TMP_DIR/ask-request.json" \
    --output "$TMP_DIR/ask-response.json" \
    "$CANDIDATE_BASE_URL/api/ask"
MEDIA_URL="$(
    python3 \
        - "$TMP_DIR/ask-response.json" "$MEDIA_PUBLIC_BASE_URL" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
media_base = sys.argv[2].rstrip("/")
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
    if media_base == "/media" and candidate.startswith("/media/"):
        print(candidate)
        break
    if media_base.startswith("https://") and candidate.startswith(media_base + "/"):
        print(candidate)
        break
else:
    raise SystemExit(
        "smoke-test: RAG response has no media URL under MEDIA_PUBLIC_BASE_URL"
    )
PY
)"

curl \
    --silent \
    --show-error \
    --fail \
    --location \
    --connect-timeout 5 \
    --max-time 90 \
    --header 'Content-Type: application/json' \
    --header 'Accept: text/event-stream' \
    --data-binary "@$TMP_DIR/ask-request.json" \
    --output "$TMP_DIR/ask-stream.txt" \
    "$CANDIDATE_BASE_URL/api/ask/stream"
python3 - "$TMP_DIR/ask-stream.txt" <<'PY'
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").replace("\r\n", "\n")
events = []
for block in text.split("\n\n"):
    if not block.strip():
        continue
    names = [
        line.partition(":")[2].strip()
        for line in block.splitlines()
        if line.startswith("event:")
    ]
    if len(names) != 1:
        raise SystemExit("smoke-test: malformed RAG SSE event block")
    events.append(names[0])
if not events:
    raise SystemExit("smoke-test: RAG SSE response has no events")
if "error" in events:
    raise SystemExit("smoke-test: RAG SSE response contains event: error")
if events[-1] != "done" or events.count("done") != 1:
    raise SystemExit(
        f"smoke-test: terminal event is not done exactly once; got {events!r}"
    )
PY

MEDIA_RETRIEVAL_URL="$(
    python3 "$OPS_HELPER" validate-media-url \
        "$APP_ENV_FILE" \
        "$PUBLIC_BASE_URL" \
        "$MEDIA_URL"
)" || die "projected media URL does not match the public origin"
fetch \
    "$MEDIA_RETRIEVAL_URL" \
    "$TMP_DIR/media-object" \
    "$TMP_DIR/media.headers" \
    30 \
    >"$TMP_DIR/media.metadata"
assert_non_html_response \
    "$TMP_DIR/media.metadata" \
    "$TMP_DIR/media-object" \
    "projected media object"

printf 'smoke tests passed\n'
