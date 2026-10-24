"""Build self-hosted Noto Serif SC subsets without losing dynamic Wiki glyphs.

Requires fonttools with WOFF2 support (the fonttools[woff] extra).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "frontend" / "react-app" / "public" / "fonts"
DEFAULT_CORPUS = ROOT / "frontend" / "react-app" / "font-corpus.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regular", type=Path, required=True, help="Complete regular source font")
    parser.add_argument("--bold", type=Path, required=True, help="Complete bold source font")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--normalize-corpus",
        action="store_true",
        help="Remove whitespace and characters unsupported by both source fonts",
    )
    return parser.parse_args()


def normalized_characters(text: str) -> set[str]:
    return {char for char in text if char == " " or not char.isspace()}


def build_subset(source: Path, destination: Path, characters: set[str]) -> None:
    font = TTFont(source)
    source_cmap = font.getBestCmap() or {}
    missing = characters - {chr(codepoint) for codepoint in source_cmap}
    if missing:
        raise ValueError(f"{source} lacks {len(missing)} corpus characters: {''.join(sorted(missing))}")

    options = subset.Options()
    options.layout_features = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(characters)))
    subsetter.subset(font)
    font.flavor = "woff2"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    font.save(temporary)
    os.replace(temporary, destination)

    generated = TTFont(destination)
    generated_cmap = generated.getBestCmap() or {}
    generated_missing = characters - {chr(codepoint) for codepoint in generated_cmap}
    if generated_missing:
        raise AssertionError(f"Generated {destination} lacks {len(generated_missing)} corpus characters")
    print(f"Built {destination.name}: {len(characters)} characters, {destination.stat().st_size} bytes")


def main() -> None:
    args = parse_args()
    characters = normalized_characters(args.corpus.read_text(encoding="utf-8"))
    if args.normalize_corpus:
        supported = set(characters)
        for source in (args.regular, args.bold):
            source_cmap = TTFont(source).getBestCmap() or {}
            supported &= {chr(codepoint) for codepoint in source_cmap}
        args.corpus.write_text("".join(sorted(supported)) + "\n", encoding="utf-8")
        characters = supported
        print(f"Normalized corpus to {len(characters)} source-supported characters")

    for weight, source in (("regular", args.regular), ("bold", args.bold)):
        build_subset(source, FONT_DIR / f"noto-serif-sc-{weight}.woff2", characters)


if __name__ == "__main__":
    main()
