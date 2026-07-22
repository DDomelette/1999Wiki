import { expect, test } from '@playwright/test'

test('suggested questions stay usable across desktop, mobile, and themes', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'responsive QA runs once with explicit viewports')

  await page.addInitScript(() => {
    localStorage.setItem('r1999-theme', JSON.stringify({
      state: { theme: 'manuscript-gold' },
      version: 2,
    }))
  })
  await page.route('**/api/categories', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ categories: [] }),
  }))
  await page.route('**/api/conversations/**', (route) => route.fulfill({ status: 204 }))
  await page.setViewportSize({ width: 2048, height: 1157 })
  await page.goto('/')
  await page.evaluate(() => {
    document.querySelector('[data-snap-section="chat"]')?.scrollIntoView()
  })

  const group = page.getByRole('group', { name: '推荐问题' })
  const input = page.getByPlaceholder('输入问题...')
  await expect(group).toBeVisible()
  await expect(group.getByRole('button')).toHaveCount(4)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'manuscript-gold')

  const initialQuestions = await group.getByRole('button').allTextContents()
  await page.getByRole('combobox').selectOption('人物')
  expect(await group.getByRole('button').allTextContents()).toEqual(initialQuestions)
  await page.getByRole('button', { name: '清空对话' }).click()
  expect(await group.getByRole('button').allTextContents()).toEqual(initialQuestions)

  const groupBox = await group.boundingBox()
  const inputBox = await input.boundingBox()
  expect(groupBox).not.toBeNull()
  expect(inputBox).not.toBeNull()
  expect(groupBox!.y + groupBox!.height).toBeLessThanOrEqual(inputBox!.y)

  const first = group.getByRole('button').first()
  const firstQuestion = await first.textContent()
  await first.click()
  await expect(input).toHaveValue(firstQuestion ?? '')
  await expect(input).toBeFocused()
  await expect(page.locator('[data-animation-slot="message-shell"]')).toHaveCount(0)

  const second = group.getByRole('button').nth(1)
  const secondQuestion = await second.textContent()
  await second.press('Enter')
  await expect(input).toHaveValue(secondQuestion ?? '')

  await page.screenshot({ path: testInfo.outputPath('suggested-questions-wide-gold.png') })
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'storm-dark'))
  await page.screenshot({ path: testInfo.outputPath('suggested-questions-wide-dark.png') })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => {
    document.querySelector('[data-snap-section="chat"]')?.scrollIntoView()
  })
  await expect(group).toBeVisible()

  const mobileMetrics = await page.locator('.suggested-questions__list').evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }))
  expect(mobileMetrics.scrollWidth).toBeGreaterThan(mobileMetrics.clientWidth)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  await expect(page.getByRole('button', { name: '发送' })).toBeVisible()
  await expect(page.getByRole('button', { name: '扩大检索' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('suggested-questions-mobile-dark.png') })

  await page.route('**/api/ask/stream', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 600))
    await route.fulfill({
      contentType: 'text/event-stream',
      body: 'event: done\ndata: {"answer":"测试回答","sources":[],"assets":[],"media":[]}\n\n',
    })
  })
  await input.fill('测试推荐问题')
  await input.press('Enter')
  await expect(group.getByRole('button').first()).toBeDisabled()
  await expect(group.getByRole('button').first()).toBeEnabled()
  expect(await group.getByRole('button').allTextContents()).toEqual(initialQuestions)
})
