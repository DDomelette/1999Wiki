import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AnimatedList } from './AnimatedList'
import { AnimatedContent } from './AnimatedContent'
import { ScrollReveal } from './ScrollReveal'

describe('React Bits adapters', () => {
  it('renders React nodes and scopes arrow handling to the focused list', () => {
    const onSelect = vi.fn()
    render(
      <AnimatedList
        items={[{ id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta' }]}
        itemKey={(item) => item.id}
        renderItem={(item) => <strong>{item.label}</strong>}
        onItemSelect={onSelect}
        ariaLabel="voices"
      />,
    )

    expect(screen.getByText('Alpha').tagName).toBe('STRONG')
    const globalEvent = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })
    window.dispatchEvent(globalEvent)
    expect(globalEvent.defaultPrevented).toBe(false)

    const list = screen.getByRole('listbox', { name: 'voices' })
    list.focus()
    fireEvent.keyDown(list, { key: 'ArrowDown' })
    fireEvent.keyDown(list, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'b' }), 1)
    expect(list).toHaveClass('reactbits-scrollbar-hidden')
    expect(list).toHaveAttribute('data-scroll-start', 'true')
  })

  it('can retain a visible scrollbar explicitly', () => {
    render(<AnimatedList items={['a']} itemKey={String} renderItem={String} displayScrollbar ariaLabel="items" />)
    expect(screen.getByRole('listbox')).not.toHaveClass('reactbits-scrollbar-hidden')
  })

  it('renders content immediately when reduced motion is requested', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
    render(<AnimatedContent direction="horizontal">Ready</AnimatedContent>)
    expect(screen.getByText('Ready')).toHaveAttribute('data-motion', 'reduced')
  })

  it('keeps reveal text readable when animation is disabled', () => {
    const { container } = render(<ScrollReveal text="Readable text" scrollContainer={null} baseRotation={0} enabled={false} />)
    expect(container.querySelector('.reactbits-scroll-reveal')).toHaveTextContent('Readable text')
  })

  it('keeps word nodes for scoped opacity and blur reveal', () => {
    const { container } = render(<ScrollReveal text="two words" scrollContainer={null} baseRotation={0} enabled />)
    expect(container.querySelectorAll('[data-reveal-word]')).toHaveLength(2)
  })
})
