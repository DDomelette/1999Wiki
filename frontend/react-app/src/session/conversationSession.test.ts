import { describe, expect, it } from 'vitest'
import { ConversationSession, CONVERSATION_STORAGE_KEY } from './conversationSession'

const UUID_A = '00000000-0000-4000-8000-000000000001'
const UUID_B = '00000000-0000-4000-8000-000000000002'
const UUID_C = '00000000-0000-4000-8000-000000000003'

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length() { return this.values.size }
  clear() { this.values.clear() }
  getItem(key: string) { return this.values.get(key) ?? null }
  key(index: number) { return [...this.values.keys()][index] ?? null }
  removeItem(key: string) { this.values.delete(key) }
  setItem(key: string, value: string) { this.values.set(key, value) }
}

type Listener = (event: MessageEvent) => void

class FakeChannel {
  private readonly listeners = new Set<Listener>()
  closed = false

  constructor(readonly name: string, private readonly peers: Set<FakeChannel>) {
    peers.add(this)
  }

  addEventListener(_type: 'message', listener: Listener) {
    this.listeners.add(listener)
  }

  removeEventListener(_type: 'message', listener: Listener) {
    this.listeners.delete(listener)
  }

  postMessage(data: unknown) {
    for (const peer of this.peers) {
      if (peer === this || peer.closed) continue
      queueMicrotask(() => peer.dispatch(data))
    }
  }

  close() {
    if (this.closed) return
    this.closed = true
    this.peers.delete(this)
    this.listeners.clear()
  }

  private dispatch(data: unknown) {
    for (const listener of this.listeners) {
      listener(new MessageEvent('message', { data }))
    }
  }
}

function channelFactory() {
  const groups = new Map<string, Set<FakeChannel>>()
  return (name: string) => {
    const peers = groups.get(name) ?? new Set<FakeChannel>()
    groups.set(name, peers)
    return new FakeChannel(name, peers) as unknown as BroadcastChannel
  }
}

function storageWith(id: string) {
  const storage = new MemoryStorage()
  storage.setItem(CONVERSATION_STORAGE_KEY, id)
  return storage
}

describe('ConversationSession', () => {
  it('generates a valid UUID when crypto.randomUUID is unavailable on HTTP', () => {
    const randomUuidDescriptor = Object.getOwnPropertyDescriptor(crypto, 'randomUUID')
    Object.defineProperty(crypto, 'randomUUID', {
      configurable: true,
      value: undefined,
    })

    try {
      const session = new ConversationSession(new MemoryStorage(), channelFactory(), undefined, 1)
      expect(session.currentId()).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      )
      session.close()
    } finally {
      if (randomUuidDescriptor) {
        Object.defineProperty(crypto, 'randomUUID', randomUuidDescriptor)
      } else {
        Reflect.deleteProperty(crypto, 'randomUUID')
      }
    }
  })

  it('reuses the same id after refresh-like reconstruction', async () => {
    const storage = new MemoryStorage()
    const channels = channelFactory()
    const first = new ConversationSession(storage, channels, () => UUID_A, 1)

    expect(await first.ready()).toBe(UUID_A)
    first.close()

    const refreshed = new ConversationSession(storage, channels, () => UUID_B, 1)
    expect(await refreshed.ready()).toBe(UUID_A)
    refreshed.close()
  })

  it('rotates a copied sessionStorage id when an existing tab answers the probe', async () => {
    const channels = channelFactory()
    const original = new ConversationSession(storageWith(UUID_A), channels, () => UUID_B, 1)
    expect(await original.ready()).toBe(UUID_A)

    const duplicate = new ConversationSession(storageWith(UUID_A), channels, () => UUID_C, 1)
    expect(await duplicate.ready()).toBe(UUID_C)
    expect(original.currentId()).toBe(UUID_A)

    duplicate.close()
    original.close()
  })

  it('repairs invalid storage and rotate always changes the id', async () => {
    const storage = storageWith('not-a-uuid')
    const ids = [UUID_A, UUID_B]
    const session = new ConversationSession(storage, channelFactory(), () => ids.shift()!, 1)

    expect(await session.ready()).toBe(UUID_A)
    expect(session.rotate()).toBe(UUID_B)
    expect(await session.ready()).toBe(UUID_B)
    session.close()
  })
})
