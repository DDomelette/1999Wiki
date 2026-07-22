export const CONVERSATION_STORAGE_KEY = 'rag.conversation_id'
const CHANNEL_NAME = 'rag.conversation_identity'
const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

type ChannelMessage = {
  type: 'probe' | 'ack'
  conversationId: string
  instanceId: string
}

type ChannelFactory = (name: string) => BroadcastChannel
type UuidFactory = () => string

function defaultUuidFactory(): string {
  return crypto.randomUUID()
}

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length() { return this.values.size }
  clear() { this.values.clear() }
  getItem(key: string) { return this.values.get(key) ?? null }
  key(index: number) { return [...this.values.keys()][index] ?? null }
  removeItem(key: string) { this.values.delete(key) }
  setItem(key: string, value: string) { this.values.set(key, value) }
}

class LocalChannel {
  addEventListener() {}
  removeEventListener() {}
  postMessage() {}
  close() {}
}

function defaultChannelFactory(name: string): BroadcastChannel {
  if (typeof BroadcastChannel === 'function') return new BroadcastChannel(name)
  return new LocalChannel() as unknown as BroadcastChannel
}

function browserStorage(): Storage {
  try {
    if (typeof sessionStorage !== 'undefined') return sessionStorage
  } catch {
    // Fall through to process-local storage when browser storage is unavailable.
  }
  return new MemoryStorage()
}

export class ConversationSession {
  private channel: BroadcastChannel | null = null
  private readyResult: Promise<string> | null = null
  private closed = false
  private acked = false
  private fallbackId: string | null = null
  private readonly instanceId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  private readonly onMessage = (event: MessageEvent<ChannelMessage>) => {
    const message = event.data
    if (!message || message.conversationId !== this.currentId()) return
    if (message.type === 'probe' && message.instanceId !== this.instanceId) {
      this.channel?.postMessage({
        type: 'ack',
        conversationId: message.conversationId,
        instanceId: message.instanceId,
      } satisfies ChannelMessage)
    } else if (message.type === 'ack' && message.instanceId === this.instanceId) {
      this.acked = true
    }
  }

  constructor(
    private readonly storage: Storage = browserStorage(),
    private readonly createChannel: ChannelFactory = defaultChannelFactory,
    private readonly createUuid: UuidFactory = defaultUuidFactory,
    private readonly probeWindowMs = 40,
  ) {}

  currentId(): string {
    let stored: string | null = null
    try {
      stored = this.storage.getItem(CONVERSATION_STORAGE_KEY)
    } catch {
      stored = this.fallbackId
    }
    if (stored && UUID_V4_RE.test(stored)) return stored
    const generated = this.nextUuid(null)
    this.store(generated)
    return generated
  }

  ready(): Promise<string> {
    if (this.readyResult) return this.readyResult
    const initialId = this.currentId()
    this.readyResult = new Promise<string>((resolve) => {
      this.ensureChannel()
      this.acked = false
      this.channel?.postMessage({
        type: 'probe',
        conversationId: initialId,
        instanceId: this.instanceId,
      } satisfies ChannelMessage)
      window.setTimeout(() => {
        resolve(this.acked && this.currentId() === initialId ? this.rotate() : this.currentId())
      }, this.probeWindowMs)
    })
    return this.readyResult
  }

  rotate(): string {
    const current = this.currentId()
    const next = this.nextUuid(current)
    this.store(next)
    this.readyResult = Promise.resolve(next)
    return next
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    if (this.channel) {
      this.channel.removeEventListener('message', this.onMessage as EventListener)
      this.channel.close()
      this.channel = null
    }
  }

  private ensureChannel(): void {
    if (this.channel || this.closed) return
    this.channel = this.createChannel(CHANNEL_NAME)
    this.channel.addEventListener('message', this.onMessage as EventListener)
  }

  private nextUuid(previous: string | null): string {
    for (let attempt = 0; attempt < 16; attempt += 1) {
      const candidate = this.createUuid()
      if (UUID_V4_RE.test(candidate) && candidate !== previous) return candidate
    }
    throw new Error('Unable to generate a distinct conversation UUID')
  }

  private store(id: string): void {
    this.fallbackId = id
    try {
      this.storage.setItem(CONVERSATION_STORAGE_KEY, id)
    } catch {
      // The in-memory fallback remains the active tab identity.
    }
  }
}

export const conversationSession = new ConversationSession()

if (typeof window !== 'undefined') {
  void conversationSession.ready()
  window.addEventListener('pagehide', () => conversationSession.close(), { once: true })
}
