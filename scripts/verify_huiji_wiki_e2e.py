"""Read-only verification for the Huiji Wiki API and media contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOCAL_PATH_MARKERS = ("D:\\", "C:\\", "file://")
INTERNAL_AUDIT_KEYS = {
    "local_relpath",
    "source_key",
    "sourceKey",
    "source_sha256",
    "sourceSha256",
    "diagnostics",
}


def find_local_path_leaks(payload: Any, path: str = "$") -> list[str]:
    leaks: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            child_path = f"{path}.{key}"
            if key in INTERNAL_AUDIT_KEYS:
                leaks.append(f"{child_path}=<forbidden key>")
            leaks.extend(find_local_path_leaks(value, child_path))
        return leaks
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            leaks.extend(find_local_path_leaks(value, f"{path}[{index}]"))
        return leaks
    if isinstance(payload, str) and any(marker in payload for marker in LOCAL_PATH_MARKERS):
        leaks.append(f"{path}={payload}")
    return leaks


def collect_media_urls(payload: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "url" and isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
            else:
                urls.extend(collect_media_urls(value))
    elif isinstance(payload, list):
        for value in payload:
            urls.extend(collect_media_urls(value))
    return urls


def load_object_keys_from_media_assets(path: str | Path) -> set[str]:
    keys: set[str] = set()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row.get("object_key", "")).strip()
            if key:
                keys.add(key)
    return keys


def load_minio_object_keys(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    with target.open("r", encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def validate_media_asset_minio_coverage(object_keys: Iterable[str], minio_keys: Iterable[str]) -> list[str]:
    available = set(minio_keys)
    return sorted(key for key in set(object_keys) if key not in available)


def validate_crawler_character_contract(
    health: Any,
    categories: Any,
    detail: Any,
    *,
    expected_pages: int,
    sample_title: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(health, dict):
        return ["wiki health is not an object"]
    if int(health.get("pageCount", 0) or 0) <= 0:
        errors.append("pageCount must be greater than zero")
    if health.get("stale") is not False:
        errors.append("wiki health stale must be false")

    category_rows = categories.get("categories", []) if isinstance(categories, dict) else []
    character_row = next(
        (
            row
            for row in category_rows
            if isinstance(row, dict) and row.get("key") == "character"
        ),
        None,
    )
    actual_pages = int(character_row.get("count", 0) or 0) if character_row else 0
    if actual_pages != expected_pages:
        errors.append(f"character page count must be {expected_pages}, got {actual_pages}")

    if not isinstance(detail, dict):
        errors.append(f"sample detail for {sample_title!r} is missing")
        return errors
    if detail.get("title") != sample_title:
        errors.append(f"sample title must be {sample_title!r}, got {detail.get('title')!r}")

    source_title = str(detail.get("sourceTitle", ""))
    if not source_title.startswith("Data:Char/"):
        errors.append(f"sample sourceTitle must start with Data:Char/, got {source_title!r}")

    content = detail.get("content") if isinstance(detail.get("content"), dict) else {}
    if content.get("crawlerProjectionVersion") != 1:
        errors.append("crawlerProjectionVersion must be 1")
    blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []
    inheritance_tables = [
        block
        for block in blocks
        if isinstance(block, dict) and block.get("section") == "inheritance" and block.get("type") == "table"
    ]
    portray_tables = [
        block
        for block in blocks
        if isinstance(block, dict) and block.get("section") == "portray" and block.get("type") == "table"
    ]
    serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
    if not inheritance_tables or "木秀于林" not in serialized:
        errors.append("inheritance table or 木秀于林 is missing")
    if not portray_tables:
        errors.append("portray table is missing")
    portray_levels: set[str] = set()
    for table in portray_tables:
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        for row in rows:
            if not isinstance(row, list) or not row:
                continue
            level = str(row[0]).strip().upper()
            if level.startswith("LV."):
                level = level[3:]
            if level in {"1", "2", "3", "4", "5"}:
                portray_levels.add(level)
    if portray_levels != {"1", "2", "3", "4", "5"}:
        errors.append("portray LV.1..LV.5 is incomplete")

    media_links = detail.get("mediaLinks") if isinstance(detail.get("mediaLinks"), list) else []
    roles = {
        str(item.get("role", ""))
        for item in media_links
        if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://"))
    }
    if "roster_avatar" not in roles:
        errors.append("roster_avatar media is missing")
    if not roles.intersection({"stage_live2d", "stage_portrait"}):
        errors.append("stage_live2d/stage_portrait media is missing")
    if "wiki-supplement" in json.dumps(detail, ensure_ascii=False).casefold():
        errors.append("legacy wiki-supplement media path is forbidden")
    return errors


def walk_opaque_page_list(
    fetch_page: Callable[[str], Any],
    *,
    expected_count: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_page_ids: set[str] = set()
    seen_cursors: set[str] = set()
    cursor = ""
    while True:
        payload = fetch_page(cursor)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            errors.append("page-list response must contain an items array")
            break
        for item in payload["items"]:
            if not isinstance(item, dict):
                errors.append("page-list item must be an object")
                continue
            page_id = str(item.get("pageId") or "")
            if not page_id:
                errors.append("page-list item is missing pageId")
            elif page_id in seen_page_ids:
                errors.append(f"duplicate pageId: {page_id}")
            else:
                seen_page_ids.add(page_id)
            items.append(item)
        next_cursor = payload.get("nextCursor")
        if next_cursor in (None, ""):
            break
        if not isinstance(next_cursor, str):
            errors.append("nextCursor must be an opaque string or null")
            break
        if next_cursor in seen_cursors:
            errors.append("opaque cursor loop detected")
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        if len(seen_cursors) > max(expected_count + 1, 2):
            errors.append("page-list traversal exceeded its safety bound")
            break
    if len(seen_page_ids) != expected_count:
        errors.append(f"unique page count must be {expected_count}, got {len(seen_page_ids)}")
    return items, errors


def validate_search_probe(payload: Any, probe: str) -> list[str]:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        return [f"search probe {probe!r} returned no items"]
    first = items[0]
    if not isinstance(first, dict) or first.get("title") != probe:
        return [f"search probe {probe!r} exact title is not the first item"]
    return []


def build_inspection_summary(
    *,
    categories: Any,
    page_items: list[Any],
    media_urls: list[str],
    leaks: list[str],
    media_failures: list[str],
    missing_object_keys: list[str],
    label: str,
    require_media: bool = False,
) -> dict[str, Any]:
    category_count = len(categories.get("categories", [])) if isinstance(categories, dict) else 0
    missing_required_media = require_media and not media_urls
    return {
        "label": label,
        "ok": not leaks and not media_failures and not missing_object_keys and not missing_required_media,
        "category_count": category_count,
        "page_count": len(page_items),
        "http_media_url_count": len(media_urls),
        "local_path_leak_count": len(leaks),
        "media_url_failure_count": len(media_failures),
        "missing_object_key_count": len(missing_object_keys),
    }


def fetch_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base_url.rstrip('/')}{path}{query}"
    with urlopen(url, timeout=15) as response:  # noqa: S310 - local verification URL is operator-provided.
        return json.loads(response.read().decode("utf-8"))


def check_http_media_sample(urls: Iterable[str], limit: int = 5) -> list[str]:
    failures: list[str] = []
    for url in list(dict.fromkeys(urls))[:limit]:
        request = Request(url, headers={"Range": "bytes=0-0"})
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - local verification URL is operator-provided.
                if response.status not in (200, 206):
                    failures.append(f"{url} -> HTTP {response.status}")
        except URLError as exc:
            failures.append(f"{url} -> {exc}")
    return failures


def run(args: argparse.Namespace) -> int:
    payloads: list[Any] = []
    health = fetch_json(args.base_url, "/api/wiki/health")
    categories = fetch_json(args.base_url, "/api/wiki/categories")
    pages = fetch_json(args.base_url, "/api/wiki/pages", {"limit": args.limit})
    payloads.extend([health, categories, pages])

    page_items = pages.get("items", []) if isinstance(pages, dict) else []
    if page_items:
        first_page_id = page_items[0].get("pageId")
        if first_page_id:
            detail = fetch_json(args.base_url, f"/api/wiki/pages/{first_page_id}")
            payloads.append(detail)

    sample_detail: Any = None
    if args.require_crawler_contract:
        route_result = fetch_json(args.base_url, "/api/wiki/routes/resolve", {"title": args.sample_title})
        payloads.append(route_result)
        sample_route = route_result.get("route", "") if isinstance(route_result, dict) else ""
        if sample_route:
            sample_detail = fetch_json(args.base_url, "/api/wiki/pages/by-route", {"route": sample_route})
            payloads.append(sample_detail)

    leaks = [leak for payload in payloads for leak in find_local_path_leaks(payload)]
    media_urls = [url for payload in payloads for url in collect_media_urls(payload)]
    media_failures = check_http_media_sample(media_urls, args.media_sample_limit) if args.check_media else []

    missing_object_keys: list[str] = []
    if args.check_minio_coverage:
        if not args.media_assets or not args.minio_object_list:
            raise ValueError("--check-minio-coverage requires --media-assets and --minio-object-list")
        object_keys = load_object_keys_from_media_assets(args.media_assets)
        minio_keys = load_minio_object_keys(args.minio_object_list)
        missing_object_keys = validate_media_asset_minio_coverage(object_keys, minio_keys)

    summary = build_inspection_summary(
        categories=categories,
        page_items=page_items,
        media_urls=media_urls,
        leaks=leaks,
        media_failures=media_failures,
        missing_object_keys=missing_object_keys,
        label=args.inspection_label,
        require_media=args.check_media,
    )
    crawler_contract_errors = (
        validate_crawler_character_contract(
            health,
            categories,
            sample_detail,
            expected_pages=args.expected_character_pages,
            sample_title=args.sample_title,
        )
        if args.require_crawler_contract
        else []
    )
    page_list_items: list[dict[str, Any]] = []
    page_list_errors: list[str] = []
    search_reports: list[dict[str, Any]] = []
    expected_page_count = 0
    if args.check_page_list:
        category_rows = categories.get("categories", []) if isinstance(categories, dict) else []
        matching_category = next(
            (
                row
                for row in category_rows
                if isinstance(row, dict) and row.get("key") == args.page_list_type
            ),
            None,
        )
        if not matching_category:
            page_list_errors.append(f"category {args.page_list_type!r} is missing")
        else:
            expected_page_count = int(matching_category.get("count", 0) or 0)

            def fetch_page(cursor: str) -> Any:
                params: dict[str, Any] = {"type": args.page_list_type, "limit": args.limit}
                if cursor:
                    params["cursor"] = cursor
                return fetch_json(args.base_url, "/api/wiki/pages", params)

            page_list_items, traversal_errors = walk_opaque_page_list(
                fetch_page,
                expected_count=expected_page_count,
            )
            page_list_errors.extend(traversal_errors)
            payloads.append(page_list_items)
        for probe in args.search_probe:
            search_payload = fetch_json(
                args.base_url,
                "/api/wiki/pages",
                {"type": args.page_list_type, "q": probe, "limit": args.limit},
            )
            probe_errors = validate_search_probe(search_payload, probe)
            page_list_errors.extend(probe_errors)
            search_reports.append(
                {
                    "probe": probe,
                    "ok": not probe_errors,
                    "firstTitle": (
                        search_payload.get("items", [{}])[0].get("title", "")
                        if isinstance(search_payload, dict) and search_payload.get("items")
                        else ""
                    ),
                    "errors": probe_errors,
                }
            )
            payloads.append(search_payload)
    health_failed = not isinstance(health, dict) or health.get("stale") is not False or health.get("pageCount", 0) <= 0
    report = {
        "wiki_media_inspection": summary,
        "health": health,
        "crawler_contract_validation": {
            "required": args.require_crawler_contract,
            "ok": not crawler_contract_errors,
            "errors": crawler_contract_errors,
            "sampleTitle": args.sample_title if args.require_crawler_contract else "",
        },
        "page_list_validation": {
            "required": args.check_page_list,
            "ok": not page_list_errors,
            "pageType": args.page_list_type if args.check_page_list else "",
            "expectedCount": expected_page_count,
            "uniqueCount": len({str(item.get('pageId') or '') for item in page_list_items if item.get('pageId')}),
            "errors": page_list_errors,
            "searchProbes": search_reports,
        },
    }

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(f"categories: {summary['category_count']}")
    print(f"pages: {summary['page_count']}")
    print(f"http media url count: {summary['http_media_url_count']}")
    print(f"local path leak count: {summary['local_path_leak_count']}")
    print(f"missing object_key count: {summary['missing_object_key_count']}")

    if leaks:
        print("local path leaks:")
        for leak in leaks[:20]:
            print(f"- {leak}")
    if media_failures:
        print("media URL failures:")
        for failure in media_failures[:20]:
            print(f"- {failure}")
    if missing_object_keys:
        print("missing object_keys:")
        for key in missing_object_keys[:20]:
            print(f"- {key}")
    if crawler_contract_errors:
        print("crawler character contract failures:")
        for error in crawler_contract_errors:
            print(f"- {error}")
    if page_list_errors:
        print("page-list validation failures:")
        for error in page_list_errors:
            print(f"- {error}")

    if args.print_json_summary:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))

    if health_failed:
        print("wiki health is stale or contains no pages")
        return 1
    if crawler_contract_errors:
        return 1
    if page_list_errors:
        return 1
    if leaks or media_failures or missing_object_keys:
        return 1
    if args.check_media and not media_urls:
        print("no HTTP media URL found")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--check-media", action="store_true")
    parser.add_argument("--media-sample-limit", type=int, default=5)
    parser.add_argument("--media-assets", default="data/processed/huiji/dev/media_assets.jsonl")
    parser.add_argument("--minio-object-list", default="")
    parser.add_argument("--check-minio-coverage", action="store_true")
    parser.add_argument("--inspection-label", default="wiki-media-inspection")
    parser.add_argument("--require-crawler-contract", action="store_true")
    parser.add_argument("--expected-character-pages", type=int, default=132)
    parser.add_argument("--sample-title", default="槲寄生")
    parser.add_argument("--check-page-list", action="store_true")
    parser.add_argument("--page-list-type", default="character")
    parser.add_argument("--search-probe", action="append", default=[])
    parser.add_argument("--print-json-summary", action="store_true")
    parser.add_argument("--output", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
