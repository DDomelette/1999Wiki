# Frontend Recovery Strategy

## Context

This document covers frontend recovery after untracked wiki and media UI source files were deleted during cleanup.

The current frontend has been made buildable again with reconstructed compatibility components. The wiki page will be rebuilt separately, so the current wiki shell should be treated as a temporary placeholder.

Git must not be used during this recovery phase. Work only through filesystem edits, searches, frontend tests, and builds.

## Scope

Frontend recovery includes:

- `frontend/react-app/src/components/wiki/*`
- `frontend/react-app/src/api/wiki.ts`
- `frontend/react-app/src/types/wiki.ts`
- `frontend/react-app/src/components/chat/MessageActions.tsx`
- `frontend/react-app/src/components/chat/VoicePanel.tsx`
- `frontend/react-app/src/components/chat/VideoPanel.tsx`
- `frontend/react-app/src/media/storyCovers.ts`

Existing caller files that survived and should guide compatibility:

- `frontend/react-app/src/App.tsx`
- `frontend/react-app/src/components/chat/MessageBubble.tsx`
- `frontend/react-app/src/components/chat/MessageAssets.tsx`
- `frontend/react-app/src/media/assets.ts`
- `frontend/react-app/src/types/index.ts`

## Current Known State

`WikiShell` exists as a placeholder route target for `/wiki`.

`api/wiki.ts` and `types/wiki.ts` exist with minimal API and DTO types.

`MessageActions`, `VoicePanel`, and `VideoPanel` exist and satisfy current tests.

`storyCovers.ts` exists with a minimal ASCII-safe resource pool so category cover tests and production build pass.

## Main Risks

The original frontend files were not recovered. Current versions are compatibility reconstructions.

The wiki UI likely lost:

- original layout
- navigation state
- page detail rendering
- relation/link interactions
- category filters
- route resolution UX
- animation/styling details

The media UI likely lost:

- original audio playback state
- progress animation behavior
- video playlist behavior
- panel grouping behavior
- accessibility details beyond current tests
- polished styling

`storyCovers.ts` is currently a placeholder list. It may reference assets that do not exist until the new asset pipeline is rebuilt.

## Repair Phases

### Phase 1: Preserve Compile Compatibility

Goal: keep the app buildable while backend and wiki page reconstruction proceeds.

Checks:

```powershell
npm --prefix frontend/react-app test -- --run src/components/chat/MessageBubble.test.tsx src/media/assets.test.ts
npm --prefix frontend/react-app run build
```

Expected current result:

```text
16 passed
build succeeds
```

### Phase 2: Keep Wiki Frontend as Temporary Shell

Goal: avoid blocking app startup while the wiki page is rebuilt from scratch.

Temporary acceptable behavior:

- `/wiki` renders without crashing.
- category list can fail gracefully when backend/MySQL is unavailable.
- page list can be empty.
- link back to main QA app works.

Do not over-invest in the current `WikiShell`. Replace it when the real wiki frontend design starts.

### Phase 3: Rebuild Wiki API Client After Backend Contract Stabilizes

Goal: align frontend API types with final backend routes.

Current routes assumed by `api/wiki.ts`:

- `GET /api/wiki/categories`
- `GET /api/wiki/pages`
- `GET /api/wiki/pages/{page_id}`
- `GET /api/wiki/routes/resolve`

After MySQL/backend rebuild, verify response shapes:

- `WikiCategoryItem`
- `WikiPageListItem`
- `WikiPageDetail`
- `WikiRouteResolveResponse`

Then update `types/wiki.ts` before rebuilding the UI.

### Phase 4: Rebuild Media Components Intentionally

Goal: replace compatibility media components with production-quality chat media UI.

Files:

- `MessageActions.tsx`
- `VoicePanel.tsx`
- `VideoPanel.tsx`
- possibly `MessageAssets.tsx` if the recovered backend media shape changes.

Required behavior:

- `MessageActions` renders omitted/failure actions and calls `runAction`.
- `VoicePanel` handles multiple voice rows, playback state, progress, and accessible labels.
- `VideoPanel` supports primary video and additional video choices.
- media rendering must not break image attachments in `MessageAssets`.

Focused tests to keep:

```powershell
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Suggested tests to add later:

```tsx
it('switches primary video when a secondary video is selected', () => {
  ...
})

it('pauses the previous voice line when another voice line starts', () => {
  ...
})

it('passes action payload to the chat store when an action button is clicked', () => {
  ...
})
```

### Phase 5: Repair Story Covers After Asset Pipeline Is Known

Goal: make story category covers point to real generated/static assets.

Current file:

- `src/media/storyCovers.ts`

Required behavior:

- exported paths must be ASCII-only.
- paths should match `/images/story/storys/[A-Za-z0-9.-]+\.(png|jpg|jpeg|webp)`.
- at least one actual file should exist under `public/images/story/storys/`.

Validation:

```powershell
npm test -- --run src/media/assets.test.ts
```

### Phase 6: Full Frontend Verification

Run:

```powershell
npm --prefix frontend/react-app test -- --run
npm --prefix frontend/react-app run build
```

If the rebuilt wiki page becomes substantial, also run browser verification against desktop and mobile widths before considering it done.

## Deferred Work

After backend wiki routes and MySQL schema are stable:

- replace the placeholder `WikiShell`.
- rebuild wiki list/detail/search views.
- add tests for route resolution and page detail states.
- verify `/wiki` under Vite dev server.

After media backend behavior is stabilized:

- redesign voice/video panels around final `MediaItem` fields.
- verify answer media from real `/ask/stream` payloads.
- add loading, error, and unavailable media states.
