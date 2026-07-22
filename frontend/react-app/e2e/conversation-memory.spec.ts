import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

interface ConversationSample {
  initial_entity_name: string
  initial_query: string
  follow_up_query: string
  expected_follow_intents: string[]
  allowed_follow_child_ids: string[]
  allowed_follow_parent_ids: string[]
  allowed_follow_media_ids: string[]
  required_follow_child_ids: string[]
}

interface SseFrame {
  event?: string
  data: Record<string, unknown> | null
}

const manifestPath = process.env.RAG_MEMORY_SAMPLE_MANIFEST
if (!manifestPath) throw new Error('RAG_MEMORY_SAMPLE_MANIFEST is required')
const manifestLine = readFileSync(manifestPath, 'utf8')
  .split(/\r?\n/)
  .find((line) => line.trim())
if (!manifestLine) throw new Error('RAG_MEMORY_SAMPLE_MANIFEST contains no samples')
const sample = JSON.parse(manifestLine) as ConversationSample

function parseSse(text: string): SseFrame[] {
  return text
    .trim()
    .split(/\r?\n\r?\n/)
    .filter(Boolean)
    .map((frame) => {
      const lines = frame.split(/\r?\n/)
      const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
      const dataLines = lines
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
      return {
        event,
        data: dataLines.length
          ? JSON.parse(dataLines.join('\n')) as Record<string, unknown>
          : null,
      }
    })
}

async function sendThroughUi(page: Page, query: string): Promise<SseFrame[]> {
  const input = page.locator('form input[type="text"]')
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/ask/stream'),
  )
  await input.fill(query)
  await input.press('Enter')
  const response = await responsePromise
  expect(response.ok()).toBe(true)
  return parseSse(await response.text())
}

function payload(frames: SseFrame[], event: string): Record<string, unknown> {
  const value = frames.find((item) => item.event === event)?.data
  expect(value, `missing ${event} SSE event`).toBeTruthy()
  return value!
}

function assertNoLocalPaths(value: unknown): void {
  expect(JSON.stringify(value)).not.toMatch(/[A-Z]:\\|file:\/\/|local_relpath/i)
}

function assertFollowPayloads(frames: SseFrame[]): void {
  const sourcesPayload = payload(frames, 'sources')
  const donePayload = payload(frames, 'done')
  expect(sourcesPayload.memory).toEqual(donePayload.memory)

  for (const value of [sourcesPayload, donePayload]) {
    const route = value.route as Record<string, unknown>
    expect(route.entity).toBe(sample.initial_entity_name)
    expect(route.requested_intents).toEqual(sample.expected_follow_intents)
    assertNoLocalPaths(value)
  }

  const sources = donePayload.sources as Array<Record<string, unknown>>
  expect(sources.length).toBeGreaterThan(0)
  for (const source of sources) {
    expect(source.name).toBe(sample.initial_entity_name)
    expect(sample.allowed_follow_child_ids).toContain(source.child_id)
    expect(sample.allowed_follow_parent_ids).toContain(source.parent_id)
  }
  expect(
    sources.some((source) => sample.required_follow_child_ids.includes(
      String(source.child_id),
    )),
  ).toBe(true)

  const media = donePayload.media as Array<Record<string, unknown>>
  for (const item of media) {
    const mediaId = item.media_id ?? item.asset_id
    expect(sample.allowed_follow_media_ids).toContain(mediaId)
  }
}

test('same tab refresh retains memory and clear rotates it', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'real conversation gate runs once')
  await page.goto('/')
  await page.evaluate(() => document.querySelector('[data-snap-section="chat"]')?.scrollIntoView())

  const first = await sendThroughUi(page, sample.initial_query)
  expect((payload(first, 'done').memory as Record<string, unknown>).status).toBe('new')
  const beforeReload = await page.evaluate(
    () => sessionStorage.getItem('rag.conversation_id'),
  )
  expect(beforeReload).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)

  await page.reload()
  await page.evaluate(() => document.querySelector('[data-snap-section="chat"]')?.scrollIntoView())
  expect(await page.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).toBe(beforeReload)
  const follow = await sendThroughUi(page, sample.follow_up_query)
  const followDone = payload(follow, 'done')
  expect((followDone.memory as Record<string, unknown>).status).toBe('hit')
  assertFollowPayloads(follow)

  const deleteResponse = page.waitForResponse(
    (response) => response.request().method() === 'DELETE'
      && response.url().includes('/api/conversations/'),
  )
  await page.getByRole('button', { name: '清空对话' }).click()
  expect((await deleteResponse).status()).toBe(204)
  await expect.poll(
    () => page.evaluate(() => sessionStorage.getItem('rag.conversation_id')),
  ).not.toBe(beforeReload)

  const afterClear = await sendThroughUi(page, sample.follow_up_query)
  const afterClearDone = payload(afterClear, 'done')
  expect((afterClearDone.memory as Record<string, unknown>).status).toBe('new')
  expect((afterClearDone.route as Record<string, unknown> | null)?.entity).not.toBe(
    sample.initial_entity_name,
  )

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})

test('duplicated tabs rotate copied session identity', async ({ context }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'duplicate-tab gate runs once')
  const copiedId = '00000000-0000-4000-8000-000000000010'
  const pageA = await context.newPage()
  const pageB = await context.newPage()
  await Promise.all(
    [pageA, pageB].map((page) => page.addInitScript(
      (id) => sessionStorage.setItem('rag.conversation_id', id),
      copiedId,
    )),
  )

  await pageA.goto('/')
  await expect.poll(
    () => pageA.evaluate(() => sessionStorage.getItem('rag.conversation_id')),
  ).toBe(copiedId)
  await pageA.waitForTimeout(100)
  await pageB.goto('/')
  await expect.poll(async () => {
    const ids = await Promise.all(
      [pageA, pageB].map((page) => page.evaluate(
        () => sessionStorage.getItem('rag.conversation_id'),
      )),
    )
    return ids[0] !== ids[1]
  }).toBe(true)
  expect(await pageA.evaluate(() => sessionStorage.getItem('rag.conversation_id'))).toBe(copiedId)
})
