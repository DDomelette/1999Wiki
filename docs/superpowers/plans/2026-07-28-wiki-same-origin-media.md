# Wiki Same-Origin Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render Wiki thumbnails and detail media when production APIs return safe same-origin `/media/...` URLs.

**Architecture:** Replace the Wiki absolute-only URL predicate with one shared public-media predicate used by list and detail view models. The predicate accepts HTTP(S) and a narrowly scoped `/media/<bucket>/<object>` path while rejecting unsafe schemes, ambiguous paths, and traversal.

**Tech Stack:** React 18, TypeScript, Vitest, Vite, Caddy, Docker, TCR/GHCR, existing Blue/Green deployment scripts.

## Global Constraints

- Preserve same-origin `/media/` delivery; do not make the backend emit an IP or domain.
- Do not change Wiki artifacts, MySQL, MinIO, Caddy, RAG media behavior, or persistent data.
- Accept only HTTP(S) or safe root-relative `/media/<bucket>/<object>` URLs.
- Reject protocol-relative URLs, unsafe schemes, query strings, fragments, backslashes, control/whitespace characters, and decoded traversal segments.
- Do not modify or stage `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`.
- Publish TCR as primary and GHCR as mirror, then deploy through the existing transactional Blue/Green workflow.

---

## File Structure

- `frontend/react-app/src/components/wiki/wikiViewModel.ts`: owns the shared Wiki public-media URL predicate and list/detail media filtering.
- `frontend/react-app/src/components/wiki/wikiViewModel.test.ts`: covers list thumbnails, general media projection, and unsafe URL rejection.
- `frontend/react-app/src/components/wiki/characterDetailViewModel.ts`: consumes the shared predicate for character portrait, skill, and collection media.
- `frontend/react-app/src/components/wiki/characterDetailViewModel.test.ts`: covers production-shaped same-origin character media.

### Task 1: Reproduce Same-Origin Media Loss

**Files:**
- Modify: `frontend/react-app/src/components/wiki/wikiViewModel.test.ts`
- Modify: `frontend/react-app/src/components/wiki/characterDetailViewModel.test.ts`

**Interfaces:**
- Consumes: `buildWikiIndexItem`, `buildWikiPageViewModel`, and `buildCharacterDetailViewModel`.
- Produces: regression tests that fail while `/media/...` URLs are discarded.

- [ ] **Step 1: Add a list and general-media regression test**

Add a test that assigns the literal thumbnail and media URL
`/media/reverse1999-assets/reverse1999/portrait/aa/example.webp`, then asserts
that `buildWikiIndexItem(page).thumbnail` and
`buildWikiPageViewModel(detail).primaryMedia?.url` retain that exact path.

- [ ] **Step 2: Add a character-detail regression test**

Create a production-shaped skin with `skinId: "300301"`, roles
`stage_live2d` and `stage_portrait`, and literal `/media/...` URLs. Assert that
`buildCharacterDetailViewModel(buildWikiPageViewModel(page))` produces one
portrait state whose two media URLs remain unchanged.

- [ ] **Step 3: Run both focused tests and verify RED**

Run:

```powershell
Set-Location frontend/react-app
npx vitest run src/components/wiki/wikiViewModel.test.ts src/components/wiki/characterDetailViewModel.test.ts
```

Expected: the new tests fail because the thumbnails, primary media, and
portrait states are empty.

### Task 2: Implement the Safe Public-Media Boundary

**Files:**
- Modify: `frontend/react-app/src/components/wiki/wikiViewModel.ts`
- Modify: `frontend/react-app/src/components/wiki/wikiViewModel.test.ts`
- Modify: `frontend/react-app/src/components/wiki/characterDetailViewModel.ts`

**Interfaces:**
- Produces: `isPublicMediaUrl(value: unknown): value is string`.
- Consumers: `isPublicImageUrl`, `toMediaViewModel`, and `buildMediaMap`.

- [ ] **Step 1: Add unsafe-path cases before implementation**

Add table-driven assertions that reject these literal values:

```text
//evil.example/image.webp
/other/image.webp
/media/
/media/bucket/../secret.webp
/media/bucket/%2e%2e/secret.webp
/media/bucket/image.webp?download=1
/media/bucket/image.webp#fragment
/media/bucket\image.webp
javascript:alert(1)
data:image/webp;base64,AAAA
```

Also assert that `/media/bucket/folder/image.webp`,
`http://example.test/image.webp`, and `https://example.test/image.webp` pass.

- [ ] **Step 2: Implement the minimal predicate**

Rename `isPublicHttpUrl` to `isPublicMediaUrl`. For absolute URLs, parse with
`new URL`, require `http:` or `https:`, a hostname, empty search/hash, and a
safe decoded pathname. For relative URLs, require the literal `/media/`
prefix, at least a bucket and object segment, and the same safety checks.
Reject malformed percent encoding, decoded dot segments, backslashes,
whitespace/control characters, query strings, and fragments.

- [ ] **Step 3: Update both consumers**

Use `isPublicMediaUrl` in `isPublicImageUrl`, `toMediaViewModel`, and
`characterDetailViewModel.ts`'s `buildMediaMap`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
npx vitest run src/components/wiki/wikiViewModel.test.ts src/components/wiki/characterDetailViewModel.test.ts
```

Expected: all focused tests pass.

- [ ] **Step 5: Run full frontend verification**

Run:

```powershell
npm test
npm run build
```

Expected: all frontend tests pass and Vite produces the production bundle.

- [ ] **Step 6: Commit the fix**

```powershell
git add -- frontend/react-app/src/components/wiki/wikiViewModel.ts frontend/react-app/src/components/wiki/wikiViewModel.test.ts frontend/react-app/src/components/wiki/characterDetailViewModel.ts frontend/react-app/src/components/wiki/characterDetailViewModel.test.ts
git commit -m "fix: render same-origin Wiki media"
```

### Task 3: Publish and Deploy the Verified Release

**Files:**
- Use unchanged: `docker/Dockerfile.frontend`
- Use unchanged: `deploy/bin/release_manifest.py`
- Use unchanged: `deploy/bin/deploy.sh`
- Use unchanged: `deploy/bin/cleanup.sh`

**Interfaces:**
- Consumes: the committed release and existing TCR/GHCR credentials.
- Produces: a digest-qualified release active in Green with Blue retained as rollback.

- [ ] **Step 1: Push `main` and run CI**

Push `main`, dispatch `publish-images.yml`, and require frontend and Python
test jobs plus both OCI build steps to pass. The known GitHub Runner-to-TCR
publish failure may be replaced by the established local push path.

- [ ] **Step 2: Build and publish images**

Build the frontend image from the exact commit with
`--platform linux/amd64 --provenance=false`. Reuse the unchanged backend image
digest under the new immutable release tag. Push both component tags to TCR
and GHCR, then verify that each component has identical digests in both
registries.

- [ ] **Step 3: Create and verify the release manifest**

Use `deploy/bin/release_manifest.py create` with both GHCR statuses set to
`published`, then verify against TCR and GHCR before transferring the manifest
to `/srv/1999wiki/releases/<release>/`.

- [ ] **Step 4: Free and deploy Green safely**

Read active state. If Green is the exact stopped recorded rollback target,
retire only that target using `deploy/bin/cleanup.sh` and its exact
confirmation token. Create the Green release environment using ports `18200`
and `18280`, then run `deploy/bin/deploy.sh <release> green`.

- [ ] **Step 5: Verify the public symptom**

From a real browser against `http://43.139.115.6/`, require:

- character-list thumbnails issue `/media/` requests and decode successfully;
- character detail portrait, skill, and collection images have nonzero
  `naturalWidth`;
- no Wiki media `requestfailed` or `pageerror` events occur;
- `/health/ready`, `/api/wiki/health`, cache headers, and all application and
  infrastructure containers remain healthy.

- [ ] **Step 6: Preserve rollback and record evidence**

Keep the previous Blue release recorded and immediately restartable. Do not
run cleanup after the successful switch.
