# 1999Wiki First-Load Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production React UI interactive before homepage media loads, reduce retained video and font payloads, enable compressed/cached static delivery, and release the change through the existing TCR-first Blue/Green workflow.

**Architecture:** `HomeSection` treats video as progressive enhancement and mounts it only after the first React render during browser idle time. Generated local media remains in the frontend image but is optimized before commit; Caddy separates immutable hashed assets, retained media, and SPA entry responses into explicit cache classes.

**Tech Stack:** React 18, TypeScript, Vitest, Python 3.11/pytest, FontTools/Brotli, FFmpeg, Vite, Caddy 2.11, Docker, Git LFS, GitHub Actions, TCR/GHCR, existing Bash Blue/Green deployment scripts.

## Global Constraints

- Runtime media remains server-local; production does not depend on COS or a CDN.
- Homepage video remains available but must never block React UI rendering.
- `pv.mp4` must be H.264/yuv420p, silent, at most 1920×1080 and 30 fps, at most 20 MiB, with `moov` before `mdat`.
- Dynamic Wiki Chinese content must retain complete Unicode coverage; do not subset fonts to characters found only in the current source tree.
- Hashed `/assets/*` responses use one-year immutable caching; `/fonts/*`, `/images/*`, and `/videos/*` use one-week caching; SPA entry responses use `no-cache`.
- TCR is the mandatory primary registry. GHCR is the mirror and may be deferred only under the existing five-transient-failure rule.
- Deploy the new release to Green, validate it, then switch traffic. Keep the current Blue release available for rollback.
- Do not stage or modify `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`.

---

## File Structure

- `frontend/react-app/src/components/sections/HomeSection.tsx` — progressive video lifecycle and fallback behavior.
- `frontend/react-app/src/components/sections/HomeSection.test.tsx` — first-render, idle activation, reduced-motion, success, and failure behavior.
- `tests/test_frontend_delivery.py` — repository-level media, font, and Caddy delivery contracts.
- `frontend/react-app/public/videos/pv.mp4` — optimized retained homepage video, still tracked through Git LFS.
- `frontend/react-app/public/fonts/noto-serif-sc-regular.woff2` — full-coverage compressed regular Chinese font.
- `frontend/react-app/public/fonts/noto-serif-sc-bold.woff2` — full-coverage compressed bold Chinese font.
- `frontend/react-app/public/fonts/noto-serif-sc-regular.otf` — removed after WOFF2 validation.
- `frontend/react-app/public/fonts/noto-serif-sc-bold.otf` — removed after WOFF2 validation.
- `frontend/react-app/src/styles/fonts.css` — WOFF2 sources, optional loading, and system fallback.
- `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css.test.ts` — updated self-hosted font inventory contract.
- `docker/frontend.Caddyfile` — compression and mutually exclusive static-cache routes.

---

### Task 1: Render the UI Before Activating the Homepage Video

**Files:**
- Modify: `frontend/react-app/src/components/sections/HomeSection.test.tsx`
- Modify: `frontend/react-app/src/components/sections/HomeSection.tsx`

**Interfaces:**
- Consumes: `HOME_VIDEO_SRC`, `GLOBAL_BACKGROUND_IMAGE_SRC`, browser `requestIdleCallback`, `cancelIdleCallback`, and `matchMedia`.
- Produces: a `HomeSection` that initially renders no `<video>`, mounts it only after idle activation, and never mounts it for `prefers-reduced-motion: reduce`.

- [ ] **Step 1: Replace the eager-video assertion with failing initial and idle-activation tests**

Add deterministic browser stubs before rendering:

```tsx
let idleCallback: (() => void) | undefined

Object.defineProperty(window, 'requestIdleCallback', {
  configurable: true,
  value: (callback: () => void) => {
    idleCallback = callback
    return 41
  },
})
Object.defineProperty(window, 'cancelIdleCallback', {
  configurable: true,
  value: vi.fn(),
})
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }),
})
```

Assert the initial DOM contains the download button but no video. Invoke `idleCallback` inside `act`, then assert that the video exists with `preload="none"`, the global poster, and `/videos/pv.mp4`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Set-Location frontend/react-app
npx vitest run src/components/sections/HomeSection.test.tsx
```

Expected: FAIL because the current component renders the video and source immediately.

- [ ] **Step 3: Add failing reduced-motion and media-failure tests**

Add one test whose `matchMedia` returns `matches: true`, trigger the captured idle callback if any, and assert no video is mounted. Add another test that activates the video, fires `error`, and asserts that the video disappears while the `立即下载` button remains.

- [ ] **Step 4: Implement the minimal deferred-media lifecycle**

In `HomeSection.tsx`, add a `videoEnabled` state and an effect:

```tsx
useEffect(() => {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

  if ('requestIdleCallback' in window) {
    const idleId = window.requestIdleCallback(() => setVideoEnabled(true), { timeout: 2000 })
    return () => window.cancelIdleCallback(idleId)
  }

  const timeoutId = window.setTimeout(() => setVideoEnabled(true), 1500)
  return () => window.clearTimeout(timeoutId)
}, [])
```

Render the `<video>` only when `videoEnabled && !videoFailed`, add `preload="none"`, and retain the existing poster, autoplay, muted, loop, inline-play, fade-in, and fallback behavior.

- [ ] **Step 5: Run focused and full frontend tests and verify GREEN**

Run:

```powershell
Set-Location frontend/react-app
npx vitest run src/components/sections/HomeSection.test.tsx
npm test
```

Expected: the focused tests and all frontend tests pass with zero failures.

- [ ] **Step 6: Commit the progressive video behavior**

```powershell
git add -- frontend/react-app/src/components/sections/HomeSection.tsx frontend/react-app/src/components/sections/HomeSection.test.tsx
git commit -m "fix: defer homepage video until after first render"
```

---

### Task 2: Transcode the Retained Homepage Video

**Files:**
- Create: `tests/test_frontend_delivery.py`
- Modify: `frontend/react-app/public/videos/pv.mp4`

**Interfaces:**
- Consumes: the checked-in Git LFS MP4 payload.
- Produces: an H.264/yuv420p, silent, faststart MP4 no larger than 20 MiB.

- [ ] **Step 1: Write the failing MP4 repository contract**

Create `tests/test_frontend_delivery.py` with a top-level MP4 atom reader:

```python
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "frontend/react-app/public/videos/pv.mp4"

def top_level_atoms(path: Path) -> list[tuple[str, int]]:
    atoms = []
    with path.open("rb") as stream:
        offset = 0
        while offset < path.stat().st_size:
            stream.seek(offset)
            size, kind = struct.unpack(">I4s", stream.read(8))
            if size == 1:
                size = struct.unpack(">Q", stream.read(8))[0]
            atoms.append((kind.decode("ascii"), offset))
            if size == 0:
                break
            offset += size
    return atoms

def test_home_video_is_small_and_faststart():
    atoms = dict(top_level_atoms(VIDEO))
    assert VIDEO.stat().st_size <= 20 * 1024 * 1024
    assert atoms["moov"] < atoms["mdat"]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_home_video_is_small_and_faststart -q
```

Expected: FAIL because the current video is about 117 MiB and its `moov` atom follows `mdat`.

- [ ] **Step 3: Inspect the source and transcode to a temporary file**

Use an FFmpeg 6+ executable and run:

```powershell
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height,avg_frame_rate,pix_fmt -of json frontend/react-app/public/videos/pv.mp4
ffmpeg -i frontend/react-app/public/videos/pv.mp4 -map 0:v:0 -vf "scale='min(1920,iw)':-2:force_original_aspect_ratio=decrease,fps=30" -c:v libx264 -preset slow -crf 30 -maxrate 1800k -bufsize 3600k -pix_fmt yuv420p -movflags +faststart -an frontend/react-app/public/videos/pv.optimized.mp4
```

If the temporary file exceeds 20 MiB, repeat with CRF 32 and `-maxrate 1400k -bufsize 2800k`. Do not replace the tracked file until ffprobe confirms H.264, yuv420p, no audio, at most 1920×1080, and at most 30 fps.

- [ ] **Step 4: Replace the tracked LFS payload and verify GREEN**

Move the validated temporary file over `pv.mp4`, then run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_home_video_is_small_and_faststart -q
git lfs status
```

Expected: the test passes and Git LFS reports the modified MP4 payload.

- [ ] **Step 5: Commit the media optimization**

```powershell
git add -- tests/test_frontend_delivery.py frontend/react-app/public/videos/pv.mp4
git commit -m "perf: optimize retained homepage video"
```

---

### Task 3: Convert Full-Coverage Chinese Fonts to WOFF2

**Files:**
- Modify: `tests/test_frontend_delivery.py`
- Create: `frontend/react-app/public/fonts/noto-serif-sc-regular.woff2`
- Create: `frontend/react-app/public/fonts/noto-serif-sc-bold.woff2`
- Delete: `frontend/react-app/public/fonts/noto-serif-sc-regular.otf`
- Delete: `frontend/react-app/public/fonts/noto-serif-sc-bold.otf`
- Modify: `frontend/react-app/src/styles/fonts.css`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css.test.ts`

**Interfaces:**
- Consumes: the two complete Noto Serif SC OTF files.
- Produces: complete WOFF2 equivalents and a CSS fallback chain that does not block rendering.

- [ ] **Step 1: Add failing font-delivery assertions**

Extend `tests/test_frontend_delivery.py`:

```python
FONT_DIR = ROOT / "frontend/react-app/public/fonts"
FONTS_CSS = ROOT / "frontend/react-app/src/styles/fonts.css"

def test_chinese_fonts_use_smaller_woff2_payloads():
    css = FONTS_CSS.read_text(encoding="utf-8")
    assert "noto-serif-sc-regular.woff2" in css
    assert "noto-serif-sc-bold.woff2" in css
    assert "noto-serif-sc-regular.otf" not in css
    assert "noto-serif-sc-bold.otf" not in css
    assert css.count("font-display: optional") == 2
    for name in ("noto-serif-sc-regular.woff2", "noto-serif-sc-bold.woff2"):
        payload = (FONT_DIR / name).read_bytes()
        assert payload[:4] == b"wOF2"
```

Update the existing character-detail font inventory test to expect the two WOFF2 names.

- [ ] **Step 2: Run both tests and verify RED**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_chinese_fonts_use_smaller_woff2_payloads -q
Set-Location frontend/react-app
npx vitest run src/components/wiki/WikiCharacterDetailPage.css.test.ts
```

Expected: both fail because CSS and inventory still reference OTF.

- [ ] **Step 3: Convert without character subsetting**

Use the installed FontTools and Brotli libraries to preserve every glyph:

```powershell
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'frontend/react-app/public/fonts/noto-serif-sc-regular.otf'); f.flavor='woff2'; f.save(r'frontend/react-app/public/fonts/noto-serif-sc-regular.woff2')"
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'frontend/react-app/public/fonts/noto-serif-sc-bold.otf'); f.flavor='woff2'; f.save(r'frontend/react-app/public/fonts/noto-serif-sc-bold.woff2')"
```

Open both generated files with `TTFont` before deleting the OTF files. Confirm the combined WOFF2 size is smaller than the original combined size.

- [ ] **Step 4: Update CSS and remove obsolete OTF payloads**

Change the two Noto sources to `url(...woff2) format('woff2')`, change only those two declarations to `font-display: optional`, update the existing inventory test, and remove both OTF files.

- [ ] **Step 5: Run font tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_chinese_fonts_use_smaller_woff2_payloads -q
Set-Location frontend/react-app
npx vitest run src/components/wiki/WikiCharacterDetailPage.css.test.ts
```

Expected: both tests pass; no CSS reference to either OTF remains.

- [ ] **Step 6: Commit the font optimization**

```powershell
git add -- tests/test_frontend_delivery.py frontend/react-app/public/fonts frontend/react-app/src/styles/fonts.css frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css.test.ts
git commit -m "perf: serve complete Chinese fonts as WOFF2"
```

---

### Task 4: Enable zstd and gzip for Compressible Frontend Responses

**Files:**
- Modify: `tests/test_frontend_delivery.py`
- Modify: `docker/frontend.Caddyfile`

**Interfaces:**
- Consumes: Caddy 2.11 response encoding.
- Produces: negotiated zstd/gzip for JS, CSS, HTML, JSON, and other Caddy-supported compressible types while leaving video Range delivery uncompressed.

- [ ] **Step 1: Add a failing Caddy compression contract**

Extend the repository test:

```python
CADDYFILE = ROOT / "docker/frontend.Caddyfile"

def test_frontend_caddy_enables_modern_compression():
    config = CADDYFILE.read_text(encoding="utf-8")
    assert "encode zstd gzip" in config
    assert "reverse_proxy backend:8000" in config
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_frontend_caddy_enables_modern_compression -q
```

Expected: FAIL because `encode zstd gzip` is absent.

- [ ] **Step 3: Add global response encoding**

Add `encode zstd gzip` immediately inside the `:8080` site block. Do not configure an encoder matcher for MP4; Caddy’s default encodable content types keep video out of response compression.

- [ ] **Step 4: Validate and verify GREEN**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_frontend_caddy_enables_modern_compression -q
docker run --rm -v "${PWD}/docker/frontend.Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile
```

Expected: test passes and Caddy reports a valid configuration.

- [ ] **Step 5: Commit compression support**

```powershell
git add -- tests/test_frontend_delivery.py docker/frontend.Caddyfile
git commit -m "perf: compress frontend text responses"
```

---

### Task 5: Add Explicit Immutable, Media, and SPA Cache Classes

**Files:**
- Modify: `tests/test_frontend_delivery.py`
- Modify: `docker/frontend.Caddyfile`

**Interfaces:**
- Consumes: Vite hashed `/assets/*`, retained `/fonts/*`, `/images/*`, `/videos/*`, and SPA fallback routes.
- Produces: mutually exclusive Caddy `handle` branches with correct `Cache-Control` behavior.

- [ ] **Step 1: Add failing cache-policy assertions**

Extend the Caddy contract:

```python
def test_frontend_caddy_has_three_cache_classes():
    config = CADDYFILE.read_text(encoding="utf-8")
    assert "/assets/*" in config
    assert "public, max-age=31536000, immutable" in config
    assert "/fonts/* /images/* /videos/*" in config
    assert "public, max-age=604800" in config
    assert 'Cache-Control "no-cache"' in config
    assert "try_files {path} /index.html" in config
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py::test_frontend_caddy_has_three_cache_classes -q
```

Expected: FAIL because no cache classes exist.

- [ ] **Step 3: Split static serving into mutually exclusive branches**

After the API proxy `handle` blocks, add:

```caddyfile
@immutable path /assets/*
handle @immutable {
	root * /srv
	header Cache-Control "public, max-age=31536000, immutable"
	file_server
}

@retained_media path /fonts/* /images/* /videos/*
handle @retained_media {
	root * /srv
	header Cache-Control "public, max-age=604800"
	file_server
}

handle {
	root * /srv
	header Cache-Control "no-cache"
	try_files {path} /index.html
	file_server
}
```

Keep health and API routes above these branches so API responses never inherit static cache headers.

- [ ] **Step 4: Validate and verify GREEN**

Run:

```powershell
python -m pytest tests/test_frontend_delivery.py -q
docker run --rm -v "${PWD}/docker/frontend.Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile
```

Expected: all delivery tests pass and Caddy validates the complete configuration.

- [ ] **Step 5: Commit cache behavior**

```powershell
git add -- tests/test_frontend_delivery.py docker/frontend.Caddyfile
git commit -m "perf: cache frontend assets by identity"
```

---

### Task 6: Verify, Publish, Deploy to Green, and Switch with Blue Retained

**Files:**
- Verify: all files changed by Tasks 1–5
- Use unchanged workflow: `.github/workflows/publish-images.yml`
- Use unchanged deployment tools: `deploy/bin/deploy.sh`, `deploy/bin/smoke-test.sh`, `deploy/bin/switch.sh`, `deploy/bin/rollback.sh`

**Interfaces:**
- Consumes: committed main-branch source and the immutable release identity computed as `sha-` plus the first seven characters of that commit.
- Produces: digest-qualified TCR/GHCR images and a validated Green production slot serving traffic while Blue remains rollback-ready.

- [ ] **Step 1: Run the complete local verification suite**

Run:

```powershell
python -m pytest -q
Set-Location frontend/react-app
npm test
npm run build
Set-Location ../..
docker build -f docker/Dockerfile.frontend -t 1999wiki-frontend:local .
docker run --rm -d --name 1999wiki-frontend-check -p 18080:8080 1999wiki-frontend:local
```

Against `http://127.0.0.1:18080`, verify:

- `/` returns `Cache-Control: no-cache`;
- a hashed JS or CSS asset returns `Cache-Control: public, max-age=31536000, immutable`;
- `Accept-Encoding: zstd, gzip` negotiates zstd or gzip for JS/CSS;
- `/videos/pv.mp4` supports a `206 Partial Content` Range response and one-week caching;
- `/health/ready` succeeds when the container is attached to the application network during compose-level verification.

Always remove the local check container after inspection.

- [ ] **Step 2: Review the exact diff and repository state**

Run:

```powershell
git diff origin/main...HEAD --check
git status --short --branch
git lfs status
```

Expected: only planned commits plus the protected untracked hardening document; the optimized MP4 has a valid LFS object.

- [ ] **Step 3: Push main and start immutable dual-registry publication**

Run:

```powershell
git push origin main
gh workflow run publish-images.yml --repo DDomelette/1999Wiki --ref main
```

Monitor the workflow until it reaches a terminal state. Require both TCR component records to be `published`; accept GHCR as either `published` or the existing `deferred_after_5_transient_failures`.

- [ ] **Step 4: Materialize the release on the server without exposing secrets**

Download the release manifest, verify its commit and image digests with the existing release tooling, and create the new release directory under `/srv/1999wiki/releases/$RELEASE_TAG`. Populate the Green release environment from the digest-qualified TCR references. Do not print environment files or registry credentials.

Set `RELEASE_TAG` from the verified manifest's `release_tag` field and use that exact value for the release directory and all deployment commands; never type or infer a different tag.

- [ ] **Step 5: Deploy and smoke-test Green**

On `ssh 1999wiki`, run the existing preflight and deployment path:

```bash
cd /srv/1999wiki/current
bash deploy/bin/deploy.sh "$RELEASE_TAG" green
```

Verify all Green application containers become healthy, then run the existing smoke test against the Green upstream. In addition, inspect response headers for `/`, hashed assets, fonts, and the MP4 Range request.

- [ ] **Step 6: Verify the original symptom in a browser**

Load the Green endpoint with cache disabled and a weak-network profile. Confirm:

1. the navigation, homepage title, and download button appear before any MP4 body is transferred;
2. the page remains interactive if the video request is blocked;
3. the video fades in after deferred activation when allowed;
4. `/wiki` renders Chinese content without missing-glyph boxes.

If any check fails, leave Blue active, inspect Green logs, and do not switch traffic.

- [ ] **Step 7: Switch traffic and retain Blue**

Use the existing switch command only after all Green checks pass:

```bash
cd /srv/1999wiki/current
bash deploy/bin/switch.sh green
```

Run the public smoke test against `http://43.139.115.6/`, confirm active release identity, container health, cache headers, API readiness, and homepage rendering. Keep the previous Blue containers and release files running or immediately restartable; do not run cleanup in this task.

- [ ] **Step 8: Record final evidence**

Report:

- commit and the exact `release_tag` recorded by the verified manifest;
- TCR and GHCR publication states without credentials;
- optimized MP4 and font sizes;
- full test/build counts;
- Green and public smoke results;
- active slot and retained Blue rollback identity.
