import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useScrollSpy } from './useScrollSpy'

const observed: Element[] = []

function Probe() {
  useScrollSpy()
  return null
}

describe('useScrollSpy', () => {
  beforeEach(() => {
    observed.length = 0
    document.body.innerHTML = '<section data-snap-section="home"></section>'
    vi.stubGlobal('IntersectionObserver', class {
      observe(el: Element) {
        observed.push(el)
      }
      disconnect() {}
    })
  })

  it('observes snap sections added after the hook mounts', async () => {
    render(<Probe />)

    const dynamicSection = document.createElement('section')
    dynamicSection.setAttribute('data-snap-section', 'data:人物')
    document.body.appendChild(dynamicSection)

    await waitFor(() => {
      expect(observed).toContain(dynamicSection)
    })
  })
})
