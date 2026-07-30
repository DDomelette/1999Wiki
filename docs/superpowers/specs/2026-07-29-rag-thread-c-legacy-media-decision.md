# Thread C C8c Legacy Media Fidelity Decision

**Status:** approved by the user and Thread D on 2026-07-30
**Scope:** classification and fidelity reporting for the 15,758 legacy active
media occurrences. This decision authorizes no download, upload, activation,
vector build, or production mutation.

## 1. Accepted evidence

The authoritative occurrence population is:

```text
data/processed/huiji/dev/media_assets.jsonl
SHA-256 256a4f02c59b700564e4968df89857d8f87930122007d1afd60e3ca78ba027dd
rows    15,758
```

The accepted C8c taxonomy is:

```text
eval/task8-c-20260730T145113Z/taxonomy.c8c-legacy-media.v1.json
SHA-256 8e4f50a7cb683e1577b5cf6b46e49d454c1a3d17ab89f6961c65c4ea3fb47d01
```

The candidate Media V3 file contains 19,400 candidate bindings and is evidence
only. It is not the active occurrence population.

The real-snapshot categories are:

| Category | Occurrences |
|---|---:|
| `preserved_binding` | 0 |
| `rekeyed_binding` | 0 |
| `source_removed_with_evidence` | 0 |
| `missing_local_bytes` | 13,414 |
| `missing_resource_metadata` | 0 |
| `ambiguous_binding` | 2,064 |
| `conflicting_binding` | 280 |

## 2. Resource identity

A legacy occurrence may use candidate resource evidence only when all of the
following are exact:

1. legacy `media_id` and SHA-1;
2. one resource-manifest row with the same SHA-1, full filename, and title;
3. candidate full filename and `crawler-resource:<sha1>:<filename>` source ref;
4. candidate `resource_id == resource:sha256:<content_sha256>`;
5. candidate size equals the manifest size;
6. the candidate binding ID recomputes from the frozen binding identity fields.

Filename stems, fuzzy title matching, ordinals, scan order, counts, first/last
match, and inferred content equivalence are forbidden.

Positive byte verification additionally requires one contained local file whose
size, SHA-1, and SHA-256 match the manifest, legacy occurrence, and candidate
resource identity. Candidate V3 metadata or protected-artifact identity does
not substitute for missing bytes.

## 3. Binding and closure identity

All Parent and Child record links must be represented as complete successor
sets. A legacy ID may fall back to itself only when that exact ID exists in the
current projection. A one-to-many successor set must never be flattened to a
single dictionary value.

One candidate binding is usable only when:

1. the exact resource test in section 2 passes;
2. exactly one current projection intent or voice source owns its
   `source_binding_token`;
3. candidate owner, page, Parent, Child, section, and media role equal that
   source relation;
4. current Parent/Child/owner closure passes;
5. candidate Parent and Child are members of the complete approved successor
   sets;
6. the candidate binding is not consumed by multiple legacy occurrences.

Multiple candidates, multiple source relations, multiple successor targets, or
duplicate candidate consumption are ambiguity, not a tie to be broken.

## 4. Classification rules

- `preserved_binding`: exactly one closed candidate, positive byte verification,
  no owner/Parent/Child transition, and no collision.
- `rekeyed_binding`: exactly one closed candidate, positive byte verification,
  every changed owner/Parent/Child identity is proven by approved record links,
  and no collision.
- `source_removed_with_evidence`: an explicit, hash-pinned source inventory or
  removal receipt proves the source relation was removed. Candidate absence is
  not removal evidence.
- `missing_local_bytes`: resource and binding evidence are unique and closed,
  but size/SHA-1/SHA-256 byte verification is absent or fails.
- `missing_resource_metadata`: exact manifest/resource identity is absent,
  duplicated, conflicting, or invalid.
- `ambiguous_binding`: candidate, source relation, successor set, or consumption
  cardinality is not exactly one.
- `conflicting_binding`: a unique candidate exists but current or transition
  owner/Parent/Child/source closure fails.

Evaluation order is:

```text
resource metadata
→ ambiguity/collision
→ closure conflict
→ missing or invalid bytes
→ preserved/rekeyed
```

Therefore missing bytes must never hide ambiguity or a closure conflict.

## 5. Fidelity and blocker contract

Every legacy occurrence appears exactly once in the occurrence ledger. Category
counts must sum to the dynamically computed active population.

The following categories are explicit non-Story media blockers:

```text
missing_local_bytes
missing_resource_metadata
ambiguous_binding
conflicting_binding
```

Fidelity output must retain category-specific blocker counts and an aggregate
`unexplained_binding_loss` equal to their sum. It must not count any of these
occurrences as preserved, rekeyed, corrected, or removed.

C8d/C9 and the later D release receipt may carry these as
`non_story_media_blockers` only after proving that Story Parent, Atom, source
refs, and migration artifacts are unaffected. They must remain blocked for
media readiness and must not be consumed by E.

## 6. Download and capacity decision

The approved decision is `defer_download`.

Planning evidence shows:

```text
13,414 uniquely linkable missing-byte resources   2,738,627,096 bytes
15,386 total unique legacy resources              3,063,303,800 bytes
```

Both totals exceed the frozen 2 GiB P1 new-media budget if all bytes are new.
Exact MinIO reuse and current cloud free space are unknown. No capacity
sufficiency claim or download is permitted.

A future download proposal must be a separate D-controlled gate with:

1. exact metadata-only MinIO object-key plus SHA/size inventory;
2. fresh `df -B1` evidence for the shared server filesystem;
3. a new create-only allowlist and SHA-256;
4. upload/staging/index/Docker overhead and the 12 GiB post-commit floor;
5. a cleanup plan limited to this operation's uncommitted staging or newly
   created, unreferenced objects;
6. separate user approval.

Existing active or production objects may not be deleted to manufacture free
space.

## 7. C8c implementation boundary

C8c may modify only the legacy media reconciliation, fidelity projection, the
tests that directly cover them, this decision, and the closure-gate status.

Implementation is test-first and must prove:

- complete successor sets;
- exact resource identity;
- each of the seven categories;
- ambiguity/conflict precedence over missing bytes;
- duplicate-consumption detection;
- positive size/SHA-1/SHA-256 verification;
- deterministic occurrence IDs and ordering;
- category-specific fidelity blockers;
- real-snapshot category parity with the accepted taxonomy.

C8c downloads no media and creates no vector, Milvus, MinIO, MySQL, active
pointer, or production write.
