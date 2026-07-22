#!/usr/bin/env python3
"""Minimal MCP-over-HTTP client for the Google Stitch MCP server.

Endpoint : https://stitch.googleapis.com/mcp
Auth     : header  X-Goog-Api-Key: <STITCH_API_KEY>   (read from environment)

Usage:
    python stitch_mcp.py ping                      # initialize only; verifies connectivity/auth
    python stitch_mcp.py list                      # tools/list -> JSON array of tools
    python stitch_mcp.py call <tool> '<json>'      # tools/call with a JSON argument object

Exit codes: 0 ok, 2 missing API key, 1 transport/protocol error.
Only stdlib is used. Stdout carries JSON; diagnostics go to stderr.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://stitch.googleapis.com/mcp"
PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "stitchi-skill", "version": "1.0.0"}
TIMEOUT = 60


def load_api_key() -> str | None:
    key = os.environ.get("STITCH_API_KEY", "").strip()
    if key:
        return key
    # Fallback: parse a .env file in the current working directory (no dependency).
    env_path = os.path.join(os.getcwd(), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("STITCH_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


def fail(msg: str, code: int = 1) -> "None":
    print(f"[stitchi] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


class StitchMcpClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session_id: str | None = None
        self._next_id = 1

    def _post(self, payload: dict, notify: bool = False):
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Goog-Api-Key": self.api_key,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid
                if notify:
                    resp.read()
                    return None
                return self._parse_response(resp)
        except urllib.error.HTTPError as e:
            snippet = ""
            try:
                snippet = e.read().decode("utf-8", "replace")[:400]
            except OSError:
                pass
            if e.code in (401, 403):
                fail(f"auth failed (HTTP {e.code}); check STITCH_API_KEY. {snippet}")
            fail(f"HTTP {e.code} from Stitch MCP. {snippet}")
        except urllib.error.URLError as e:
            fail(f"cannot reach {ENDPOINT}: {e.reason}")

    @staticmethod
    def _parse_response(resp) -> dict:
        raw = resp.read().decode("utf-8", "replace")
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            result: dict | None = None
            for line in raw.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                    result = msg  # keep the last JSON-RPC response frame
            if result is None:
                fail("SSE stream ended without a JSON-RPC response frame")
            return result
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            fail(f"unparseable response (Content-Type: {ctype}): {raw[:300]}")

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        req_id = self._next_id
        self._next_id += 1
        payload: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        resp = self._post(payload)
        if "error" in resp:
            err = resp["error"]
            fail(f"JSON-RPC error {err.get('code')}: {err.get('message')}")
        return resp.get("result", {})

    def initialize(self) -> dict:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notify=True)
        return result

    def list_tools(self) -> list:
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in ("ping", "list", "call"):
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    command = argv[1]

    api_key = load_api_key()
    if not api_key:
        fail("STITCH_API_KEY is not set (and no .env fallback found). "
             "Export it first, e.g.  set STITCH_API_KEY=...", code=2)

    client = StitchMcpClient(api_key)

    if command == "ping":
        result = client.initialize()
        server = result.get("serverInfo", {})
        print(json.dumps({
            "ok": True,
            "serverInfo": server,
            "protocolVersion": result.get("protocolVersion"),
        }, ensure_ascii=False, indent=2))
        return

    client.initialize()

    if command == "list":
        tools = client.list_tools()
        print(json.dumps({"ok": True, "tools": tools}, ensure_ascii=False, indent=2))
        return

    # command == "call"
    if len(argv) < 4:
        fail("usage: stitch_mcp.py call <tool_name> '<json_arguments>'", code=2)
    tool_name = argv[2]
    try:
        arguments = json.loads(argv[3])
    except json.JSONDecodeError as e:
        fail(f"arguments must be valid JSON: {e}", code=2)
    if not isinstance(arguments, dict):
        fail("arguments JSON must be an object", code=2)
    result = client.call_tool(tool_name, arguments)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
