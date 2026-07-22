import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearConversation } from './conversation'

describe('clearConversation', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))

  it('uses the encoded conversation endpoint and DELETE', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ status: 204 } as Response)

    await clearConversation('00000000-0000-4000-8000-000000000001')

    expect(fetch).toHaveBeenCalledWith(
      '/api/conversations/00000000-0000-4000-8000-000000000001',
      { method: 'DELETE' },
    )
  })

  it('rejects non-204 responses', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ status: 503 } as Response)

    await expect(clearConversation('id')).rejects.toThrow('HTTP 503')
  })
})
