from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import jieba


ANALYZER_SCHEMA_VERSION = "rag.bm25-analyzer/v1"
ANALYZER_NAME = "zh-domain-word-bigram"
ANALYZER_VERSION = "1"
SEGMENTER_NAME = "jieba"
SEGMENTER_VERSION = "0.42.1"
DEFAULT_DICTIONARY_PATH = (
    Path(__file__).resolve().parent / "resources" / "bm25_domain_terms.v1.txt"
)
_HAN_SPAN_RE = re.compile(r"[\u4e00-\u9fff]+")
_TECHNICAL_ATOM_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"[A-Za-z][A-Za-z0-9_]{0,31}:[A-Za-z][A-Za-z0-9_]{0,31}/[A-Za-z0-9_-]{1,64}"
    r"|[A-Za-z0-9]{1,32}(?:-[A-Za-z0-9]{1,64})+"
    r"|[A-Za-z0-9_]{1,64}[\u4e00-\u9fffA-Za-z0-9_-]{0,96}\.[A-Za-z0-9]{1,10}"
    r")(?![A-Za-z0-9_])"
)
_ASCII_PART_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9_]{1,64}(?![A-Za-z0-9_])")
_CHANNEL_PRIORITY = {
    "protected": 0,
    "word": 1,
    "bigram": 2,
    "technical": 3,
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_dictionary_term(value: object) -> str:
    term = unicodedata.normalize("NFKC", str(value)).strip()
    if any(unicodedata.category(character) == "Cc" for character in term):
        raise ValueError("dictionary term contains an illegal control character")
    return term


def _canonicalize_terms(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(sorted({
        term
        for value in values
        if (term := _normalize_dictionary_term(value))
    }))


def load_dictionary_terms(path: str | Path) -> tuple[str, ...]:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ValueError(f"dictionary file is missing: {target.name}") from error
    except UnicodeDecodeError as error:
        raise ValueError(f"dictionary file is not valid UTF-8: {target.name}") from error
    except OSError as error:
        raise ValueError(f"dictionary file cannot be read: {target.name}") from error
    return _canonicalize_terms(text.splitlines())


@dataclass(frozen=True)
class AnalyzerConfig:
    unicode_normalization: str = "NFKC"
    ascii_lowercase: bool = True
    segmenter_hmm: bool = False
    emit_han_bigrams: bool = True
    preserve_identifiers: bool = True
    preserve_filenames: bool = True
    technical_pattern_version: str = "1"
    merge_rule_version: str = "1"

    def to_dict(self) -> dict[str, object]:
        return {
            "unicode_normalization": self.unicode_normalization,
            "ascii_lowercase": self.ascii_lowercase,
            "segmenter_hmm": self.segmenter_hmm,
            "emit_han_bigrams": self.emit_han_bigrams,
            "preserve_identifiers": self.preserve_identifiers,
            "preserve_filenames": self.preserve_filenames,
            "technical_pattern_version": self.technical_pattern_version,
            "merge_rule_version": self.merge_rule_version,
        }


@dataclass(frozen=True)
class AnalyzerIdentity:
    schema_version: str
    name: str
    version: str
    segmenter_name: str
    segmenter_version: str
    segmenter_hmm: bool
    config: AnalyzerConfig
    config_sha256: str
    dictionary_terms: tuple[str, ...]
    dictionary_sha256: str
    fingerprint_sha256: str

    @classmethod
    def create(
        cls,
        *,
        config: AnalyzerConfig,
        dictionary_terms: Iterable[object],
    ) -> "AnalyzerIdentity":
        terms = _canonicalize_terms(dictionary_terms)
        config_payload = config.to_dict()
        config_sha256 = _sha256(_canonical_json_bytes(config_payload))
        dictionary_bytes = "".join(f"{term}\n" for term in terms).encode("utf-8")
        dictionary_sha256 = _sha256(dictionary_bytes)
        fingerprint_payload = {
            "schema_version": ANALYZER_SCHEMA_VERSION,
            "name": ANALYZER_NAME,
            "version": ANALYZER_VERSION,
            "segmenter": {
                "name": SEGMENTER_NAME,
                "version": SEGMENTER_VERSION,
                "hmm": False,
            },
            "config": config_payload,
            "config_sha256": config_sha256,
            "dictionary_terms": list(terms),
            "dictionary_sha256": dictionary_sha256,
        }
        return cls(
            schema_version=ANALYZER_SCHEMA_VERSION,
            name=ANALYZER_NAME,
            version=ANALYZER_VERSION,
            segmenter_name=SEGMENTER_NAME,
            segmenter_version=SEGMENTER_VERSION,
            segmenter_hmm=False,
            config=config,
            config_sha256=config_sha256,
            dictionary_terms=terms,
            dictionary_sha256=dictionary_sha256,
            fingerprint_sha256=_sha256(_canonical_json_bytes(fingerprint_payload)),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AnalyzerIdentity":
        required = {
            "schema_version",
            "name",
            "version",
            "segmenter",
            "config",
            "config_sha256",
            "dictionary_terms",
            "dictionary_sha256",
            "fingerprint_sha256",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"analyzer identity missing fields: {', '.join(missing)}")
        segmenter = value["segmenter"]
        config_value = value["config"]
        terms_value = value["dictionary_terms"]
        if not isinstance(segmenter, Mapping):
            raise ValueError("analyzer identity segmenter is invalid")
        if not isinstance(config_value, Mapping):
            raise ValueError("analyzer identity config is invalid")
        if not isinstance(terms_value, list) or any(
            not isinstance(term, str) for term in terms_value
        ):
            raise ValueError("analyzer identity dictionary_terms is invalid")
        try:
            config = AnalyzerConfig(**dict(config_value))
        except TypeError as error:
            raise ValueError("analyzer identity config is unsupported") from error
        if (
            value["schema_version"] != ANALYZER_SCHEMA_VERSION
            or value["name"] != ANALYZER_NAME
            or value["version"] != ANALYZER_VERSION
            or segmenter.get("name") != SEGMENTER_NAME
            or segmenter.get("version") != SEGMENTER_VERSION
            or segmenter.get("hmm") is not False
            or config != AnalyzerConfig()
        ):
            raise ValueError("analyzer identity version or config is unsupported")
        rebuilt = cls.create(config=config, dictionary_terms=terms_value)
        for field_name in (
            "config_sha256",
            "dictionary_sha256",
            "fingerprint_sha256",
        ):
            if value[field_name] != getattr(rebuilt, field_name):
                raise ValueError(f"analyzer identity {field_name} mismatch")
        if rebuilt.dictionary_terms != tuple(terms_value):
            raise ValueError("analyzer identity dictionary_terms are not canonical")
        return rebuilt

    @property
    def dictionary_bytes(self) -> bytes:
        return "".join(f"{term}\n" for term in self.dictionary_terms).encode("utf-8")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "segmenter": {
                "name": self.segmenter_name,
                "version": self.segmenter_version,
                "hmm": self.segmenter_hmm,
            },
            "config": self.config.to_dict(),
            "config_sha256": self.config_sha256,
            "dictionary_terms": list(self.dictionary_terms),
            "dictionary_sha256": self.dictionary_sha256,
            "fingerprint_sha256": self.fingerprint_sha256,
        }


@dataclass(frozen=True)
class _PositionedToken:
    segment_index: int
    start_offset: int
    end_offset: int
    channel: str
    token: str

    @property
    def dedupe_key(self) -> tuple[int, int, int, str]:
        return (
            self.segment_index,
            self.start_offset,
            self.end_offset,
            self.token,
        )

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]:
        return (
            self.segment_index,
            self.start_offset,
            _CHANNEL_PRIORITY[self.channel],
            -self.end_offset,
            self.token,
        )


def _new_jieba_tokenizer() -> jieba.Tokenizer:
    tokenizer = jieba.Tokenizer()
    tokenizer.FREQ, tokenizer.total = tokenizer.gen_pfdict(tokenizer.get_dict_file())
    tokenizer.initialized = True
    return tokenizer


class ChineseBM25Analyzer:
    def __init__(
        self,
        *,
        dictionary_path: str | Path = DEFAULT_DICTIONARY_PATH,
        extra_terms: Iterable[object] = (),
        config: AnalyzerConfig | None = None,
    ) -> None:
        selected_config = config or AnalyzerConfig()
        if selected_config != AnalyzerConfig():
            raise ValueError("unsupported Chinese BM25 analyzer config")
        installed_version = importlib.metadata.version(SEGMENTER_NAME)
        if installed_version != SEGMENTER_VERSION:
            raise ValueError(
                f"unsupported jieba version: expected {SEGMENTER_VERSION}, "
                f"got {installed_version}"
            )
        terms = _canonicalize_terms(
            (*load_dictionary_terms(dictionary_path), *tuple(extra_terms))
        )
        tokenizer = _new_jieba_tokenizer()
        for term in terms:
            tokenizer.add_word(term)
        self._tokenizer = tokenizer
        self.identity = AnalyzerIdentity.create(
            config=selected_config,
            dictionary_terms=terms,
        )

    def analyze(self, text: str) -> list[str]:
        return [
            token.token
            for token in self._analyze_segment(str(text), segment_index=0)
        ]

    def analyze_segments(self, segments: Iterable[str]) -> list[str]:
        return [
            token.token
            for segment_index, segment in enumerate(segments)
            for token in self._analyze_segment(str(segment), segment_index=segment_index)
        ]

    def _analyze_segment(
        self,
        text: str,
        *,
        segment_index: int,
    ) -> list[_PositionedToken]:
        normalized = unicodedata.normalize(
            self.identity.config.unicode_normalization,
            text,
        )
        if self.identity.config.ascii_lowercase:
            normalized = normalized.lower()
        candidates = [
            *self._protected_tokens(normalized, segment_index),
            *self._word_tokens(normalized, segment_index),
            *self._bigram_tokens(normalized, segment_index),
            *self._technical_tokens(normalized, segment_index),
        ]
        selected: dict[tuple[int, int, int, str], _PositionedToken] = {}
        for candidate in candidates:
            current = selected.get(candidate.dedupe_key)
            if (
                current is None
                or _CHANNEL_PRIORITY[candidate.channel]
                < _CHANNEL_PRIORITY[current.channel]
            ):
                selected[candidate.dedupe_key] = candidate
        return sorted(selected.values(), key=lambda token: token.sort_key)

    def _protected_tokens(
        self,
        text: str,
        segment_index: int,
    ) -> list[_PositionedToken]:
        tokens: list[_PositionedToken] = []
        for term in sorted(
            self.identity.dictionary_terms,
            key=lambda value: (-len(value), value),
        ):
            start = text.find(term)
            while start >= 0:
                tokens.append(
                    _PositionedToken(
                        segment_index,
                        start,
                        start + len(term),
                        "protected",
                        term,
                    )
                )
                start = text.find(term, start + 1)
        return tokens

    def _word_tokens(
        self,
        text: str,
        segment_index: int,
    ) -> list[_PositionedToken]:
        tokens: list[_PositionedToken] = []
        for span in _HAN_SPAN_RE.finditer(text):
            for word, relative_start, relative_end in self._tokenizer.tokenize(
                span.group(0),
                mode="default",
                HMM=False,
            ):
                if word:
                    tokens.append(
                        _PositionedToken(
                            segment_index,
                            span.start() + relative_start,
                            span.start() + relative_end,
                            "word",
                            word,
                        )
                    )
        return tokens

    def _bigram_tokens(
        self,
        text: str,
        segment_index: int,
    ) -> list[_PositionedToken]:
        tokens: list[_PositionedToken] = []
        for span in _HAN_SPAN_RE.finditer(text):
            value = span.group(0)
            for offset in range(len(value) - 1):
                tokens.append(
                    _PositionedToken(
                        segment_index,
                        span.start() + offset,
                        span.start() + offset + 2,
                        "bigram",
                        value[offset : offset + 2],
                    )
                )
        return tokens

    def _technical_tokens(
        self,
        text: str,
        segment_index: int,
    ) -> list[_PositionedToken]:
        tokens = [
            _PositionedToken(
                segment_index,
                match.start(),
                match.end(),
                "technical",
                match.group(0),
            )
            for match in _TECHNICAL_ATOM_RE.finditer(text)
        ]
        tokens.extend(
            _PositionedToken(
                segment_index,
                match.start(),
                match.end(),
                "technical",
                match.group(0),
            )
            for match in _ASCII_PART_RE.finditer(text)
        )
        return tokens


__all__ = [
    "AnalyzerConfig",
    "AnalyzerIdentity",
    "ChineseBM25Analyzer",
    "load_dictionary_terms",
]
