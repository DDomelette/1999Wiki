# Thread B BM25 Shadow Comparison

Date: 2026-07-29

Mode: shadow only

Production activation: not run

## Outcome

All B5 hard gates passed. The Chinese analyzer recovered both approved core Chinese
targets and the approved OOV bigram target. English, numeric, internal-ID, box-ID,
and filename queries retained their approved targets. This run built only temporary
fixture indexes, saved and reloaded both index formats before comparison, and did
not build or activate a production candidate.

## Identity

- Fixture: 9 records and 14 queries; records SHA-256 `8915355262c6c365c75bb0d2ac4a6dbc493d5ddb04003f3607895835fdbef319`; queries SHA-256 `c078f15931df6dcc44ac14a45230dbbf335b633e8b1aad8aecc2fe6519294700`.
- Analyzer: `rag.bm25-analyzer/v1`, `zh-domain-word-bigram` version `1`, Jieba `0.42.1`, HMM disabled.
- Analyzer hashes: config `7a6d73ccf4506e8a2992fc243529705b71b6212e86d72ff54ad57e0f29e3ff6b`; dictionary `16a5b55ca29da7c49cb76cdb6a1fd4f69a30ee66b0f1412ee964d876b6df1d3c`; fingerprint `f27a961348b208cf7e23fd280aea82344a86abeab5fb7078a290353abcd20b9b`.
- Dictionary terms: `十四行诗`, `基础资料`, `技能`, `暴雨`, `槲寄生`, `神秘学家`, `艺术品`, `重返未来:1999`.

## Query Results

Scores are reported to 12 decimal places. Each top-k cell is ordered and formatted
as `ID (score)`.

| Query | Classification | Legacy tokens | Legacy top-k | Chinese tokens | Chinese top-k |
|---|---|---|---|---|---|
| `core-mistletoe-profile` | improvement | `槲寄生的基础资料` | none | `槲寄生`, `槲寄`, `寄生`, `生的`, `的`, `的基`, `基础资料`, `基础`, `础资`, `资料` | `char:3074/profile:1` (10.074960285986); `char:3041/skill:30410111` (0); `event:star-voyage:1` (0) |
| `core-sonetto-skill` | improvement | `十四行诗的技能是什么` | none | `十四行诗`, `十四`, `四行`, `行诗`, `诗的`, `的`, `的技`, `技能`, `能是`, `是`, `是什`, `什么` | `char:3041/skill:30410111` (6.834345287167); `char:3074/profile:1` (0); `event:star-voyage:1` (0) |
| `oov-star-voyage` | oov_bigram_recovery | `星海远航` | none | `星海`, `海远`, `远航` | `event:star-voyage:1` (4.219864204157); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) |
| `no-improvement-english` | no_improvement | `matilda`, `portrait` | `english:matilda:1` (3.973026146358); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) | `matilda`, `portrait` | `english:matilda:1` (4.995821072571); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) |
| `ranking-change-mistletoe` | ranking_change | `槲寄生`, `alpha` | `ranking:alpha:1` (2.769518226111); `char:3074/profile:1` (1.986513073179); `char:3041/skill:30410111` (0) | `槲寄生`, `槲寄`, `寄生`, `alpha` | `char:3074/profile:1` (4.317840122566); `ranking:alpha:1` (3.060722089663); `char:3041/skill:30410111` (0) |
| `technical-english` | technical_non_regression | `matilda` | `english:matilda:1` (1.986513073179); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) | `matilda` | `english:matilda:1` (2.497910536286); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) |
| `technical-numeric` | technical_non_regression | `304502` | `number:304502:1` (1.451617132063); `story:304502:1` (1.131668866220); `char:3074/profile:1` (0) | `304502` | `number:304502:1` (1.825313801248); `story:304502:1` (1.430695248131); `char:3074/profile:1` (0) |
| `technical-story-id` | technical_non_regression | `data`, `story`, `304502` | `story:304502:1` (4.229007617054); `number:304502:1` (1.451617132063); `char:3074/profile:1` (0) | `data:story/304502`, `data`, `story`, `304502` | `story:304502:1` (7.304340752938); `number:304502:1` (1.825313801248); `char:3074/profile:1` (0) |
| `technical-skill-id` | technical_non_regression | `skill-30410111` | `char:3041/skill:30410111` (1.740477050354); `char:3074/profile:1` (0); `event:star-voyage:1` (0) | `skill-30410111`, `skill`, `30410111` | `char:3041/skill:30410111` (4.100607172300); `char:3074/profile:1` (0); `event:star-voyage:1` (0) |
| `technical-box-id` | technical_non_regression | `000-box-construction` | `common:box:1` (1.986513073179); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) | `000-box-construction`, `000`, `box`, `construction` | `common:box:1` (7.831527339742); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) |
| `technical-filename` | technical_non_regression | `banner_`, `今夜星光灿烂`, `png` | `media:banner:1` (4.646008126251); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) | `banner_今夜星光灿烂.png`, `banner_`, `今夜`, `夜星`, `星光灿烂`, `星光`, `光灿`, `灿烂`, `png` | `media:banner:1` (12.953520367697); `char:3074/profile:1` (0); `char:3041/skill:30410111` (0) |
| `multi-segment-sonetto` | multi_segment | `十四行诗`, `技能` | `char:3041/skill:30410111` (3.480954100708); `char:3074/profile:1` (0); `event:star-voyage:1` (0) | `十四行诗`, `十四`, `四行`, `行诗`, `技能` | `char:3041/skill:30410111` (6.834345287167); `char:3074/profile:1` (0); `event:star-voyage:1` (0) |
| `zero-result` | zero_result | `火星量子猫` | none | `火星`, `星量`, `量子`, `子猫`, `猫` | none |
| `punctuation-only` | punctuation | none | none | none | none |

The multi-segment query does not emit the cross-segment token `诗技`.

## Payload And Provenance

- Semantic fixture corpus SHA-256 is unchanged at `563db4be710c257cff19c8925f95c10c28b219f70a51d1b60507764959987eb2`.
- Legacy records-only payload: 1,504 bytes, SHA-256 `68e3287a9b30b58609d5e2fbdcb6caea9adccf03d43ffed29ff9c361df607ad0`.
- Chinese local v2 payload: 2,135 bytes, SHA-256 `941b514fedb7e31a1efb6ce0bcdbad66a9ee9a112520d7aa07682fed77fa0b7d`.
- Chinese child v3 payload: 2,541 bytes, SHA-256 `cff35df47f8efda72e8f40896b68f571a23ec8737deab374691e61fc4d4386ff`.
- Provenance semantic SHA-256 remains `59dec938bd2ed83756d4ae29f593ae3b3e86dd63ac4affc615bcaff359265024`, while payload SHA and analyzer provenance change from records-only/`legacy-regex/v1` to `huiji.bm25-index/v3`/`rag.bm25-analyzer/v1`.

## Distribution And Timing

- Legacy document token counts: `[3, 4, 3, 3, 3, 5, 5, 3, 1]`, total 30.
- Chinese document token counts: `[11, 12, 5, 3, 3, 6, 11, 6, 1]`, total 58.
- Token expansion ratio: `1.9333333333333333`.
- Sample build times: legacy `0.002453199995215982` seconds; Chinese `0.7863494000048377` seconds.
- Query timings are retained in the machine-checkable block. All timing values are descriptive only and are excluded from deterministic hashes and outcome gates.

## Commands And Risks

- Shadow test: `D:\Anaconda32024\envs\1999wiki\python.exe -m pytest -q tests/test_chinese_bm25_shadow.py`.
- Full regression: `D:\Anaconda32024\envs\1999wiki\python.exe -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py tests/test_chinese_bm25_shadow.py tests/test_huiji_corpus_artifacts.py tests/test_huiji_provenance.py tests/test_runtime_requirements.py tests/test_backend_provenance_gate.py tests/test_retriever.py tests/test_hybrid_retriever.py --basetemp=.tmp/rag-b-site/.pytest-b5-full`.
- Uncovered risks: the fixture is intentionally small and is not a production traffic distribution; timing samples are not production SLA evidence; Jieba behavior outside the approved fixture vocabulary remains unbenchmarked.

<!-- shadow-result-json
{
  "fixture_identity": {
    "queries_sha256": "c078f15931df6dcc44ac14a45230dbbf335b633e8b1aad8aecc2fe6519294700",
    "query_count": 14,
    "record_count": 9,
    "records_sha256": "8915355262c6c365c75bb0d2ac4a6dbc493d5ddb04003f3607895835fdbef319"
  },
  "analyzer_identity": {
    "config": {
      "ascii_lowercase": true,
      "emit_han_bigrams": true,
      "merge_rule_version": "1",
      "preserve_filenames": true,
      "preserve_identifiers": true,
      "segmenter_hmm": false,
      "technical_pattern_version": "1",
      "unicode_normalization": "NFKC"
    },
    "config_sha256": "7a6d73ccf4506e8a2992fc243529705b71b6212e86d72ff54ad57e0f29e3ff6b",
    "dictionary_sha256": "16a5b55ca29da7c49cb76cdb6a1fd4f69a30ee66b0f1412ee964d876b6df1d3c",
    "dictionary_terms": ["十四行诗", "基础资料", "技能", "暴雨", "槲寄生", "神秘学家", "艺术品", "重返未来:1999"],
    "fingerprint_sha256": "f27a961348b208cf7e23fd280aea82344a86abeab5fb7078a290353abcd20b9b",
    "name": "zh-domain-word-bigram",
    "schema_version": "rag.bm25-analyzer/v1",
    "segmenter": {"hmm": false, "name": "jieba", "version": "0.42.1"},
    "version": "1"
  },
  "payloads": {
    "chinese_child_v3_bytes": 2541,
    "chinese_child_v3_sha256": "cff35df47f8efda72e8f40896b68f571a23ec8737deab374691e61fc4d4386ff",
    "chinese_local_v2_bytes": 2135,
    "chinese_local_v2_sha256": "941b514fedb7e31a1efb6ce0bcdbad66a9ee9a112520d7aa07682fed77fa0b7d",
    "legacy_records_only_bytes": 1504,
    "legacy_records_only_sha256": "68e3287a9b30b58609d5e2fbdcb6caea9adccf03d43ffed29ff9c361df607ad0",
    "semantic_corpus_sha256": "563db4be710c257cff19c8925f95c10c28b219f70a51d1b60507764959987eb2"
  },
  "provenance": {
    "chinese_analyzer_fingerprint_sha256": "f27a961348b208cf7e23fd280aea82344a86abeab5fb7078a290353abcd20b9b",
    "chinese_analyzer_schema": "rag.bm25-analyzer/v1",
    "chinese_payload_schema": "huiji.bm25-index/v3",
    "chinese_payload_sha256": "cff35df47f8efda72e8f40896b68f571a23ec8737deab374691e61fc4d4386ff",
    "chinese_semantic_sha256": "59dec938bd2ed83756d4ae29f593ae3b3e86dd63ac4affc615bcaff359265024",
    "legacy_analyzer_schema": "legacy-regex/v1",
    "legacy_payload_schema": "records-only",
    "legacy_payload_sha256": "68e3287a9b30b58609d5e2fbdcb6caea9adccf03d43ffed29ff9c361df607ad0",
    "legacy_semantic_sha256": "59dec938bd2ed83756d4ae29f593ae3b3e86dd63ac4affc615bcaff359265024"
  },
  "token_distribution": {
    "chinese_counts": [11, 12, 5, 3, 3, 6, 11, 6, 1],
    "chinese_total": 58,
    "expansion_ratio": 1.9333333333333333,
    "legacy_counts": [3, 4, 3, 3, 3, 5, 5, 3, 1],
    "legacy_total": 30
  },
  "hard_gates": {
    "core-mistletoe-profile": true,
    "core-sonetto-skill": true,
    "oov-star-voyage": true,
    "technical-box-id": true,
    "technical-english": true,
    "technical-filename": true,
    "technical-numeric": true,
    "technical-skill-id": true,
    "technical-story-id": true
  },
  "commands": [
    "D:\\Anaconda32024\\envs\\1999wiki\\python.exe -m pytest -q tests/test_chinese_bm25_shadow.py",
    "D:\\Anaconda32024\\envs\\1999wiki\\python.exe -m pytest -q tests/test_chinese_bm25_analyzer.py tests/test_sparse_bm25.py tests/test_chinese_bm25_shadow.py tests/test_huiji_corpus_artifacts.py tests/test_huiji_provenance.py tests/test_runtime_requirements.py tests/test_backend_provenance_gate.py tests/test_retriever.py tests/test_hybrid_retriever.py --basetemp=.tmp/rag-b-site/.pytest-b5-full"
  ],
  "results": {
    "production_activation": "not_run",
    "shadow_test": "passed"
  },
  "uncovered_risks": [
    "Shadow fixture is intentionally small and not a production traffic distribution.",
    "Timing samples are descriptive and are not production SLA evidence.",
    "Jieba dictionary behavior outside approved fixture vocabulary remains unbenchmarked."
  ],
  "deterministic_sha256": "3931f525872099a628297c95399de5fe1022b91cc07bf9d2f61c40744b206754",
  "queries_sha256": "2ad1a2ad9e8f6d877658fa9977c47fa99a2728cd32ed5e802018801ab4a6f574",
  "document_tokens_sha256": "12ef0e7ed8d96878967ac8bd03e514e3233e9eac702f9bfe795e1bb36a2dfc13",
  "shadow_only": true,
  "activated": false,
  "timings": {
    "descriptive_only": true,
    "legacy_build_seconds": 0.002453199995215982,
    "chinese_build_seconds": 0.7863494000048377,
    "query_samples": {
      "core-mistletoe-profile": {
        "legacy_seconds": 2.4999957531690598e-05,
        "chinese_seconds": 0.00010430003749206662
      },
      "core-sonetto-skill": {
        "legacy_seconds": 7.599999662488699e-06,
        "chinese_seconds": 9.889999637380242e-05
      },
      "multi-segment-sonetto": {
        "legacy_seconds": 1.4699995517730713e-05,
        "chinese_seconds": 7.119996007531881e-05
      },
      "no-improvement-english": {
        "legacy_seconds": 2.0000035874545574e-05,
        "chinese_seconds": 3.779999678954482e-05
      },
      "oov-star-voyage": {
        "legacy_seconds": 7.90000194683671e-06,
        "chinese_seconds": 5.1799986977130175e-05
      },
      "punctuation-only": {
        "legacy_seconds": 2.5999615900218487e-06,
        "chinese_seconds": 1.0700023267418146e-05
      },
      "ranking-change-mistletoe": {
        "legacy_seconds": 1.98000343516469e-05,
        "chinese_seconds": 6.659998325631022e-05
      },
      "technical-box-id": {
        "legacy_seconds": 1.0199961252510548e-05,
        "chinese_seconds": 2.9399991035461426e-05
      },
      "technical-english": {
        "legacy_seconds": 1.1800031643360853e-05,
        "chinese_seconds": 2.6799971237778664e-05
      },
      "technical-filename": {
        "legacy_seconds": 1.71000137925148e-05,
        "chinese_seconds": 0.00013310002395883203
      },
      "technical-numeric": {
        "legacy_seconds": 1.5400000847876072e-05,
        "chinese_seconds": 3.4100026823580265e-05
      },
      "technical-skill-id": {
        "legacy_seconds": 1.8499966245144606e-05,
        "chinese_seconds": 3.15000070258975e-05
      },
      "technical-story-id": {
        "legacy_seconds": 1.7200014553964138e-05,
        "chinese_seconds": 0.00017409998690709472
      },
      "zero-result": {
        "legacy_seconds": 6.799993570894003e-06,
        "chinese_seconds": 5.129998316988349e-05
      }
    }
  }
}
shadow-result-json -->
