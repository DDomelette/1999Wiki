import { expect, test, type Locator, type Page } from '@playwright/test'

async function expectLoadedImage(image: Locator) {
  await expect(image).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0)
}

async function expectLoadedImages(images: Locator, minimum: number) {
  const count = await images.count()
  expect(count).toBeGreaterThanOrEqual(minimum)
  for (let index = 0; index < count; index += 1) {
    const image = images.nth(index)
    await expect.poll(
      () => image.evaluate((node: HTMLImageElement) => node.complete ? node.naturalWidth : 0),
      { timeout: 30_000 },
    ).toBeGreaterThan(0)
  }
}

function auditWikiRequests(page: Page) {
  const violations: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/wiki/') && request.method() !== 'GET') {
      violations.push(`${request.method()} ${request.url()}`)
    }
  })
  return violations
}

test('active media v3 serves the approved character selection and dossier', async ({ page, request }) => {
  const violations = auditWikiRequests(page)

  const healthResponse = await request.get('/api/wiki/health')
  expect(healthResponse.ok()).toBeTruthy()
  expect(await healthResponse.json()).toMatchObject({
    ready: true,
    pageCount: 7456,
    categoryCount: 4,
    mediaResourceCount: 19132,
    mediaBindingCount: 19400,
    sourceMode: 'active',
    buildVersion: 'crawler-v3-20260721t051246z',
    artifactSchemaVersion: 'evb.media-asset/v3',
    activationEpoch: 1,
    stale: false,
  })

  const detailResponse = await request.get('/api/wiki/pages/by-route?route=%2Fwiki%2Fcharacter%2F3003')
  expect(detailResponse.ok()).toBeTruthy()
  const detailPayload = await detailResponse.json()
  expect(detailPayload.mediaLinks.length).toBeGreaterThan(1)
  for (const media of detailPayload.mediaLinks) {
    expect(media.bindingId).toMatch(/^binding:sha256:/)
    expect(media.resourceId).toMatch(/^resource:sha256:/)
    expect(media).not.toHaveProperty('objectKey')
    expect(media).not.toHaveProperty('localRelpath')
  }

  await page.goto('/wiki/character')
  await expect(page.getByTestId('wiki-character-selection')).toBeVisible()
  await expect(page.getByTestId('wiki-page-index')).toContainText('30 / 132')
  await expectLoadedImage(page.getByTestId('selection-preview').locator('img'))

  await page.getByRole('button', { name: '查看完整档案' }).click()
  await expect(page).toHaveURL(/\/wiki\/character\/3003$/)
  await expect(page.getByTestId('wiki-character-detail')).toBeVisible()
  await expect(page.locator('.character-progression--inheritance')).toContainText('木秀于林')
  await expect(page.locator('.character-progression--portray')).toContainText('5')
  await expectLoadedImage(page.getByTestId('character-portrait-stage').locator('img.is-active'))
  await expect(page.locator('.character-portrait-stage__wardrobe [role="group"]').nth(1).locator('button')).toHaveCount(4)
  await expectLoadedImages(page.getByTestId('character-portrait-image'), 4)
  await expectLoadedImages(page.getByTestId('character-skill-card').locator('img'), 3)
  await expectLoadedImages(page.getByTestId('character-collection-item').locator('img'), 9)
  await expectLoadedImages(page.getByTestId('character-udimo-media'), 1)
  await expect(page.locator('.character-voice-record')).toHaveCount(49)
  await expect(page.locator('.character-voice-record audio')).toHaveCount(49)
  const voiceSources = await page.locator('.character-voice-record audio').evaluateAll((nodes) => (
    nodes.map((node) => (node as HTMLAudioElement).currentSrc || (node as HTMLAudioElement).src)
  ))
  expect(voiceSources.every((url) => /^https?:\/\//.test(url))).toBeTruthy()

  const stage = page.getByTestId('character-portrait-stage')
  const activePortrait = stage.locator('img.is-active')
  const modeButtons = stage.locator('.character-portrait-stage__wardrobe [role="group"]').first().locator('button')
  const skinButtons = stage.locator('.character-portrait-stage__wardrobe [role="group"]').nth(1).locator('button')
  await expect(modeButtons).toHaveCount(2)
  await expect(modeButtons.nth(0)).toBeEnabled()
  await expect(modeButtons.nth(1)).toBeEnabled()
  const live2dUrl = await activePortrait.getAttribute('src')
  await modeButtons.nth(1).click()
  await expect.poll(() => activePortrait.getAttribute('src')).not.toBe(live2dUrl)
  await skinButtons.nth(2).click()
  await expect.poll(() => stage.evaluate((node) => getComputedStyle(node).backgroundImage)).toContain('url(')

  if (page.viewportSize()!.width <= 760) {
    await expect(page.getByTestId('mobile-character-dossier')).toBeVisible()
    await expect(page.locator('[data-mobile-module="inheritance"]')).toBeVisible()
    await expect(page.locator('[data-mobile-module="portray"]')).toBeVisible()
  } else {
    await expect(page.getByTestId('desktop-character-dossier')).toBeVisible()
    await expect(page.getByTestId('profile-skill-rail')).toBeVisible()
    await expect(page.getByTestId('inheritance-voice-rail')).toBeVisible()
  }

  expect(violations).toEqual([])
})
