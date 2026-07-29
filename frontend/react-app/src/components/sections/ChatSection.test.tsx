import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatSection } from './ChatSection'
import { useChatStore } from '../../store/chatStore'

describe('ChatSection', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    useChatStore.setState({
      messages: [],
      category: null,
      sending: false,
      abortController: null,
      routeOptions: { expanded: false, freeSupplement: false },
    })
  })

  it('provides a return-home button that uses semantic main navigation', () => {
    const { container } = render(
      <main className="snap-container">
        <section data-snap-section="home" />
        <ChatSection />
      </main>,
    )
    const scroller = container.querySelector('.snap-container') as HTMLElement
    const homeSection = container.querySelector('[data-snap-section="home"]') as HTMLElement
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    Object.defineProperty(scroller, 'scrollTop', { configurable: true, value: 400 })
    scroller.getBoundingClientRect = vi.fn(() => ({ top: 20 }) as DOMRect)
    homeSection.getBoundingClientRect = vi.fn(() => ({ top: -380 }) as DOMRect)

    fireEvent.click(screen.getByRole('button', { name: '返回首页' }))

    expect(scrollTo).toHaveBeenCalledWith({ behavior: 'smooth', top: 0 })
    expect(window.location.hash).toBe('#home')
  })

  it('does not cover the global background with a solid section fill', () => {
    const { container } = render(<ChatSection />)
    const section = container.querySelector('[data-snap-section="chat"]') as HTMLElement

    expect(section).toHaveClass('chat-section')
    expect(section).not.toHaveAttribute('style')
  })

  it('keeps the empty state, category selector, message scroll area, and input workflow available', () => {
    render(<ChatSection />)

    expect(screen.getByText('神秘学问答')).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveValue('')
    expect(screen.getByTestId('chat-message-scroll')).toHaveAttribute('data-page-wheel-lock', 'true')
    expect(screen.getByPlaceholderText('输入问题...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '扩大检索' })).toHaveAttribute('aria-pressed', 'false')
    expect(within(screen.getByRole('group', { name: '推荐问题' })).getAllByRole('button')).toHaveLength(4)
  })

  it('keeps suggested questions available after the conversation has messages', () => {
    useChatStore.setState({
      messages: [{ id: 'user-1', role: 'user', content: '测试问题' }],
    })

    render(<ChatSection />)

    expect(screen.getByRole('group', { name: '推荐问题' })).toBeInTheDocument()
  })

  it('renders an accessible stable clear icon button', () => {
    render(<ChatSection />)

    const clear = screen.getByRole('button', { name: '清空对话' })
    expect(clear).toHaveAttribute('title', '清空对话')
    expect(clear).toHaveClass('chat-section__clear')
  })

  it('exposes a responsive toolbar and scroll layout', () => {
    const { container } = render(<ChatSection />)
    const toolbar = container.querySelector('.chat-section__toolbar')

    expect(container.querySelector('.chat-section')).toBeInTheDocument()
    expect(toolbar).toBeInTheDocument()
    expect(screen.getByRole('combobox').closest('.chat-section__toolbar')).toBe(toolbar)
    expect(container.querySelector('.chat-section__clear')).toBeInTheDocument()
    expect(container.querySelector('.chat-section__home')).toBeInTheDocument()
    expect(container.querySelector('.chat-section__messages')).toHaveAttribute('data-page-wheel-lock', 'true')
  })
})
