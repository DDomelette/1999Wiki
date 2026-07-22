// @vitest-environment node

import { describe, expect, it } from 'vitest'
import type { ProxyOptions, UserConfig, UserConfigFn } from 'vite'
import viteConfig from './vite.config'

async function resolvedConfig(): Promise<UserConfig> {
  return (viteConfig as UserConfigFn)({
    command: 'serve',
    mode: 'test',
    isSsrBuild: false,
    isPreview: false,
  })
}

function proxiedPath(entry: string | ProxyOptions, path: string): string {
  return typeof entry === 'string' || !entry.rewrite ? path : entry.rewrite(path)
}

describe('Vite API proxy routing', () => {
  it('keeps media and wiki prefixes while preserving the Ask rewrite', async () => {
    const config = await resolvedConfig()
    const proxy = config.server?.proxy as Record<string, string | ProxyOptions>

    expect(Object.keys(proxy).slice(0, 3)).toEqual(['/api/media', '/api/wiki', '/api'])
    expect(proxiedPath(proxy['/api/media'], '/api/media/voice/page?cursor=x')).toBe(
      '/api/media/voice/page?cursor=x',
    )
    expect(proxiedPath(proxy['/api'], '/api/ask/stream')).toBe('/ask/stream')
    expect(proxiedPath(proxy['/api/wiki'], '/api/wiki/pages')).toBe('/api/wiki/pages')
  })
})
