import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = process.cwd()

describe('formal frontend scope', () => {
  it('does not ship retired frontend implementations', () => {
    const retired = [
      '../../kimi_web',
      '../streamlit_app.py',
      '../gradio_app.py',
      '../html',
      'src/components/wiki-preview',
      'e2e/wiki-kimi-preview.spec.ts',
    ]

    for (const relativePath of retired) {
      expect(existsSync(join(root, relativePath)), relativePath).toBe(false)
    }

    const app = readFileSync(join(root, 'src/App.tsx'), 'utf8')
    const shell = readFileSync(
      join(root, 'src/components/wiki/WikiShell.tsx'),
      'utf8',
    )
    expect(app).not.toContain('/wiki-preview')
    expect(app).not.toContain('kimi-preview')
    expect(shell).not.toContain('wiki-preview')
    expect(shell).not.toContain('kimi-preview')
  })
})
