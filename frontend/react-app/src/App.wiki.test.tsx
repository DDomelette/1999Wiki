import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('/wiki route', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/')
    vi.unstubAllGlobals()
  })

  it('renders WikiShell outside the three-screen snap flow', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], nextCursor: null }) }))
    window.history.pushState({}, '', '/wiki')

    const { container } = render(<App />)

    await waitFor(() => expect(screen.getByTestId('wiki-shell')).toBeInTheDocument())
    expect(container.querySelector('.snap-container')).not.toBeInTheDocument()
  })

  it('does not treat /wiki-preview as a formal Wiki route', async () => {
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValue({ ok: true, json: async () => ({ categories: [] }) }))
    window.history.pushState({}, '', '/wiki-preview/character')

    const { container } = render(<App />)

    await waitFor(() => expect(container.querySelector('.snap-container')).toBeInTheDocument())
    expect(screen.queryByTestId('wiki-shell')).not.toBeInTheDocument()
  })

  it('responds to popstate instead of freezing the route from the first render', async () => {
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], nextCursor: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: [] }) }))
    window.history.replaceState({}, '', '/wiki/character')
    const { container } = render(<App />)
    await waitFor(() => expect(screen.getByTestId('wiki-shell')).toBeInTheDocument())

    act(() => {
      window.history.pushState({}, '', '/')
      window.dispatchEvent(new PopStateEvent('popstate', { state: {} }))
    })

    await waitFor(() => expect(container.querySelector('.snap-container')).toBeInTheDocument())
    expect(screen.queryByTestId('wiki-shell')).not.toBeInTheDocument()
  })
})
