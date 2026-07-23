import { defineConfig, devices } from '@playwright/test'

const jsonOutputFile = process.env.PLAYWRIGHT_JSON_OUTPUT_FILE
  || '../../eval/stitch-wiki-p0/playwright-report.json'

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['json', { outputFile: jsonOutputFile }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'stitch-wide', use: { ...devices['Desktop Chrome'], viewport: { width: 2560, height: 1440 } } },
    { name: 'stitch-desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 1024 } } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'narrow', use: { ...devices['Desktop Chrome'], viewport: { width: 900, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } },
    { name: 'mobile-webkit', use: { ...devices['iPhone 13'], viewport: { width: 390, height: 844 } } },
    { name: 'reduced-motion', use: { ...devices['Desktop Chrome'], viewport: { width: 1200, height: 900 }, reducedMotion: 'reduce' } },
    { name: 'webgl-fallback', use: { ...devices['Desktop Chrome'], viewport: { width: 1200, height: 900 } } },
  ],
})
