"""Plan Wiki thumbnails, or explicitly write them to an isolated MinIO prefix."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_wiki.snapshot import resolve_wiki_snapshot
from src.huiji_wiki.thumbnails import THUMBNAIL_PREFIX, build_thumbnail_plan, refuse_thumbnail_collision, validate_apply_confirmation


def _write_atomic_new(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-width", type=int, default=480)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-prefix", default="")
    args = parser.parse_args()
    try:
        validate_apply_confirmation(args.apply, args.confirm_prefix)
    except ValueError as exc:
        parser.error(str(exc))

    cfg = get_config()
    snapshot = resolve_wiki_snapshot(cfg, PROJECT_ROOT, PROJECT_ROOT / "data/processed/huiji/evidence/wiki-thumbnails")
    with snapshot.media_assets.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    plan = build_thumbnail_plan(rows, cfg.assets.public_base_url, cfg.assets.bucket_name, max_width=args.max_width, limit=args.limit)
    plan["snapshotSha256"] = snapshot.snapshot_sha256

    if args.apply:
        from PIL import Image
        from minio import Minio

        client = Minio(cfg.assets.endpoint.removeprefix("http://").removeprefix("https://"), access_key=cfg.assets.access_key, secret_key=cfg.assets.secret_key, secure=cfg.assets.secure)
        for entry in plan["entries"]:
            key = str(entry["thumbnailObjectKey"])
            refuse_thumbnail_collision(client, cfg.assets.bucket_name, key)
            with urlopen(str(entry["sourceUrl"]), timeout=30) as response:
                source = response.read()
            image = Image.open(io.BytesIO(source)).convert("RGBA")
            image.thumbnail((args.max_width, args.max_width * 2))
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=82, method=6)
            body = output.getvalue()
            client.put_object(cfg.assets.bucket_name, key, io.BytesIO(body), len(body), content_type="image/webp")
            entry["status"] = "uploaded"
        plan["mode"] = "apply"

    _write_atomic_new(args.output, plan)
    print(f"mode={plan['mode']} entries={len(plan['entries'])} output={args.output}")


if __name__ == "__main__":
    main()
