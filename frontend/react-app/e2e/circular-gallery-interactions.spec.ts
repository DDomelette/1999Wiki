import { expect, test, type Page } from '@playwright/test'

function svgDataUrl(color: string, label: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="800" viewBox="0 0 640 800"><rect width="640" height="800" fill="${color}"/><text x="320" y="420" fill="white" font-size="180" text-anchor="middle">${label}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

const assets = [
  { asset_id: 'one', role: 'image', alt: '短标题', url: svgDataUrl('#8a4b2a', '1') },
  { asset_id: 'two', role: 'image', alt: '这是一个用于验证按钮不会跟随文件名移动的非常长的图片标题', url: svgDataUrl('#365f57', '2') },
  { asset_id: 'three', role: 'image', alt: '第三张', url: svgDataUrl('#65507c', '3') },
]

async function openMockGallery(page: Page) {
  await page.route('**/api/categories', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ categories: [] }),
  }))
  await page.route('**/api/conversations/**', (route) => route.fulfill({ status: 204 }))
  await page.route('**/api/ask/stream', (route) => route.fulfill({
    contentType: 'text/event-stream',
    body: `event: done\ndata: ${JSON.stringify({
      answer: '画廊交互测试：以下图片用于验证滑动、吸附、固定按钮和全屏查看器交互。'.repeat(4),
      sources: [],
      assets,
      media: [],
    })}\n\n`,
  }))
  await page.goto('/')
  await page.locator('[data-snap-section="chat"]').evaluate((element) => {
    element.scrollIntoView({ block: 'start' })
  })
  const input = page.locator('.chat-input__field')
  await input.fill('显示测试图片')
  await input.press('Enter')
  const gallery = page.locator('.circular-gallery').last()
  await expect(gallery).toBeVisible()
  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', '短标题')
  return gallery
}

test('desktop controls stay fixed and viewer close remains unobstructed', async ({ page }, testInfo) => {
  test.skip(!['desktop', 'narrow'].includes(testInfo.project.name), 'desktop geometry runs at wide and narrow widths')
  const gallery = await openMockGallery(page)
  await gallery.scrollIntoViewIfNeeded()
  const previous = gallery.getByRole('button', { name: '上一张图片' })
  const next = gallery.getByRole('button', { name: '下一张图片' })
  const beforePrevious = await previous.boundingBox()
  const beforeNext = await next.boundingBox()

  await next.click()
  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', assets[1].alt)
  const afterPrevious = await previous.boundingBox()
  const afterNext = await next.boundingBox()
  for (const [before, after] of [[beforePrevious, afterPrevious], [beforeNext, afterNext]] as const) {
    expect(before).not.toBeNull()
    expect(after).not.toBeNull()
    expect(Math.abs(after!.x - before!.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(after!.y - before!.y)).toBeLessThanOrEqual(1)
  }

  const viewport = gallery.locator('.circular-gallery__viewport')
  const viewportBox = await viewport.boundingBox()
  expect(viewportBox).not.toBeNull()
  await page.mouse.move(viewportBox!.x + viewportBox!.width / 2, viewportBox!.y + viewportBox!.height / 2)
  await page.keyboard.down('Shift')
  await page.mouse.wheel(0, -120)
  await page.keyboard.up('Shift')
  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', assets[0].alt)

  const ctrlWheel = await viewport.evaluate((element) => {
    const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, ctrlKey: true, deltaY: 120 })
    const dispatched = element.dispatchEvent(event)
    return { dispatched, defaultPrevented: event.defaultPrevented }
  })
  expect(ctrlWheel).toEqual({ dispatched: true, defaultPrevented: false })
  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', assets[0].alt)

  await gallery.getByRole('button', { name: 'Open current image' }).click()
  const dialog = page.getByRole('dialog', { name: assets[0].alt })
  const close = dialog.getByRole('button', { name: 'Close image viewer' })
  await expect(dialog).toBeVisible()
  expect(await dialog.evaluate((element) => element.parentElement === document.body)).toBe(true)
  const navBox = await page.locator('.card-nav--main .card-nav__bar').boundingBox()
  const closeBox = await close.boundingBox()
  expect(navBox).not.toBeNull()
  expect(closeBox).not.toBeNull()
  expect(closeBox!.y).toBeGreaterThanOrEqual(navBox!.y + navBox!.height)
  expect(await close.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return hit === element || element.contains(hit)
  })).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('circular-gallery-desktop-viewer.png') })
  await close.click()
  await expect(dialog).toHaveCount(0)
})

test('mobile pointer drag snaps the next image to the viewport center', async ({ page }, testInfo) => {
  test.skip(!['mobile', 'mobile-webkit'].includes(testInfo.project.name), 'touch geometry runs in mobile browsers')
  const gallery = await openMockGallery(page)
  await gallery.scrollIntoViewIfNeeded()
  const viewport = gallery.locator('.circular-gallery__viewport')
  const current = gallery.locator('[data-gallery-position="current"]')
  const currentBox = await current.boundingBox()
  expect(currentBox).not.toBeNull()

  await page.mouse.move(currentBox!.x + currentBox!.width * 0.7, currentBox!.y + currentBox!.height * 0.5)
  await page.mouse.down()
  await page.mouse.move(currentBox!.x + currentBox!.width * 0.25, currentBox!.y + currentBox!.height * 0.5, { steps: 10 })
  await page.mouse.up()

  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', assets[1].alt)
  await expect.poll(() => viewport.evaluate(
    (element) => element.style.getPropertyValue('--gallery-drag-offset'),
  )).toBe('0px')
  const centers = await gallery.evaluate((element) => {
    const viewportRect = element.querySelector('.circular-gallery__viewport')!.getBoundingClientRect()
    const currentRect = element.querySelector('[data-gallery-position="current"]')!.getBoundingClientRect()
    return {
      viewport: viewportRect.left + viewportRect.width / 2,
      current: currentRect.left + currentRect.width / 2,
    }
  })
  expect(Math.abs(centers.current - centers.viewport)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: testInfo.outputPath('circular-gallery-mobile-snapped.png') })
})

test('reduced motion commits a drag without a transition', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'reduced-motion', 'reduced-motion policy runs once')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const gallery = await openMockGallery(page)
  await gallery.scrollIntoViewIfNeeded()
  const currentBox = await gallery.locator('[data-gallery-position="current"]').boundingBox()
  expect(currentBox).not.toBeNull()

  await page.mouse.move(currentBox!.x + currentBox!.width * 0.7, currentBox!.y + currentBox!.height * 0.5)
  await page.mouse.down()
  await page.mouse.move(currentBox!.x + currentBox!.width * 0.25, currentBox!.y + currentBox!.height * 0.5, { steps: 4 })
  await page.mouse.up()

  await expect(gallery.locator('[data-gallery-position="current"] img')).toHaveAttribute('alt', assets[1].alt)
  await expect(gallery.locator('[data-gallery-position="current"]')).toHaveCSS('transition-duration', '0s')
})
