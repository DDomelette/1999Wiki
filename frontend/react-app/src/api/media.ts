import type { VoicePanelPage } from '../types'

export class VoicePageError extends Error {
  readonly status: number
  readonly reloadFirstPage: boolean

  constructor(status: number, message: string) {
    super(message)
    this.name = 'VoicePageError'
    this.status = status
    this.reloadFirstPage = status === 409
  }
}

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = await response.json() as { detail?: unknown }
    if (typeof body.detail === 'string' && body.detail) return body.detail
  } catch {
    // Fall back to the status when the server did not return JSON.
  }
  return `HTTP ${response.status}`
}

export async function fetchVoicePage(cursor: string, signal?: AbortSignal): Promise<VoicePanelPage> {
  const response = await fetch(
    `/api/media/voice/page?cursor=${encodeURIComponent(cursor)}`,
    { method: 'GET', signal },
  )
  if (!response.ok) {
    throw new VoicePageError(response.status, await responseMessage(response))
  }
  return response.json() as Promise<VoicePanelPage>
}
