# Wiki Same-Origin Media Rendering Design

## Status

Approved for implementation on 2026-07-28. The user approved the proposed
same-origin media fix after production diagnosis.

## Problem

Production Wiki APIs intentionally return media as same-origin paths such as:

```text
/media/reverse1999-assets/reverse1999/portrait/e9/example.webp
```

The frontend currently accepts only absolute `http://` or `https://` URLs.
Consequently, Wiki thumbnails and detail media are discarded while building
view models, no `<img>` request is emitted, and the UI renders its fallback.
The Caddy `/media/` proxy, MinIO objects, and RAG media path are healthy.

## Approaches Considered

1. **Central safe frontend validator (selected).** Accept HTTP(S) URLs and
   root-relative paths restricted to `/media/`, while rejecting protocol
   relative URLs, traversal, query/fragment ambiguity, backslashes, and unsafe
   schemes. This preserves same-origin deployment and fixes every Wiki media
   consumer through one boundary.
2. **Make the backend emit absolute URLs.** Rejected because it couples
   artifacts to the current IP/domain and conflicts with environment-driven
   deployment and future HTTPS migration.
3. **Resolve every relative URL with `new URL(value, location.origin)`.**
   Rejected because it would accept unrelated relative paths and spread
   security policy across consumers.

## Design

Replace the absolute-only Wiki helper with a public-media URL predicate:

- accept `http://host/path` and `https://host/path`;
- accept root-relative `/media/<bucket>/<object>`;
- reject `/media` without an object path;
- reject `//host/path`, `javascript:`, `data:`, backslashes, control or
  whitespace characters, query strings, fragments, and decoded traversal
  segments including encoded dot segments;
- keep the original URL unchanged so the browser uses same-origin delivery.

Both list thumbnails and detail media maps must use this single predicate.
No backend, database, artifact, Caddy, MinIO, or RAG changes are required.

## Verification

TDD coverage must prove:

1. a list item with a production `/media/...webp` thumbnail renders it;
2. character portrait/skill/collection view models retain production
   `/media/...` links;
3. unsafe paths and schemes remain rejected;
4. the full frontend test suite and production build pass;
5. a production-container browser test observes actual Wiki image requests and
   successfully decoded images from the public IP.

## Release

Publish immutable frontend and backend release tags to TCR and GHCR, verify
digests, retire only the recorded stopped Green rollback target when required
to free the slot, deploy the candidate to Green, run existing smoke tests, and
switch only after public Wiki image verification succeeds. Preserve the prior
Blue release as the new rollback target after switching.
