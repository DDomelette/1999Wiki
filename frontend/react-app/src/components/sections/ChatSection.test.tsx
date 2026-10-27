import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

  afterEach(() => {
    vi.restoreAllMocks()
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
    expect(screen.getByRole('combobox', { name: '检索范围' })).toHaveValue('')
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
    expect(clear).toBeDisabled()
  })

  it('requires confirmation before clearing an existing conversation', () => {
    const clear = vi.fn(async () => undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    useChatStore.setState({
      messages: [{ id: 'user-1', role: 'user', content: '保留这个问题' }],
      clear,
    })
    render(<ChatSection />)

    fireEvent.click(screen.getByRole('button', { name: '清空对话' }))

    expect(window.confirm).toHaveBeenCalledWith('确定清空当前对话吗？此操作无法撤销。')
    expect(clear).not.toHaveBeenCalled()
    expect(useChatStore.getState().messages).toHaveLength(1)
  })

  it('keeps the reading position when a streamed answer grows above the viewport', () => {
    const messages = [
      { id: 'user-1', role: 'user' as const, content: 'question' },
      { id: 'assistant-1', role: 'assistant' as const, content: 'partial', streaming: true, phase: 'generating' as const },
    ]
    useChatStore.setState({ messages })
    const { container } = render(<ChatSection />)
    const scroller = screen.getByTestId('chat-message-scroll')
    let scrollTop = 0
    Object.defineProperty(scroller, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value: number) => { scrollTop = value },
    })
    Object.defineProperty(scroller, 'scrollHeight', { configurable: true, value: 1000 })
    Object.defineProperty(scroller, 'clientHeight', { configurable: true, value: 400 })

    fireEvent.scroll(scroller)
    act(() => {
      useChatStore.setState({
        messages: messages.map((message) => message.id === 'assistant-1'
          ? { ...message, content: 'partial with more text' }
          : message),
      })
    })

    expect(scrollTop).toBe(0)
    expect(container.querySelector('.chat-section__messages')).toBe(scroller)
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
