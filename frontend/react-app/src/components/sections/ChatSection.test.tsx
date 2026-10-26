import { act, fireEvent, render, screen, within } from '@testing-library/react'
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
    expect(screen.getByRole('group', { name: '可检索档案类别' })).toBeInTheDocument()
    expect(screen.getByText('QUERY_ENTRY')).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveTextContent('全部')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
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

  it('preserves the reading position when an assistant message grows away from the bottom', () => {
    useChatStore.setState({
      messages: [
        { id: 'user-1', role: 'user', content: '测试问题' },
        { id: 'assistant-1', role: 'assistant', content: '部分回答', streaming: true },
      ],
    })
    render(<ChatSection />)
    const scroller = screen.getByTestId('chat-message-scroll')
    Object.defineProperties(scroller, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    })

    fireEvent.scroll(scroller)
    act(() => {
      useChatStore.setState((state) => ({
        messages: state.messages.map((message) => message.id === 'assistant-1'
          ? { ...message, content: `${message.content}，继续生成` }
          : message),
      }))
    })

    expect(scroller.scrollTop).toBe(100)
  })

  it('keeps following new messages when the reader is near the bottom', () => {
    render(<ChatSection />)
    const scroller = screen.getByTestId('chat-message-scroll')
    Object.defineProperties(scroller, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 650 },
    })

    fireEvent.scroll(scroller)
    act(() => {
      useChatStore.setState({
        messages: [{ id: 'user-1', role: 'user', content: '测试问题' }],
      })
    })

    expect(scroller.scrollTop).toBe(1000)
  })

  it('returns to the bottom for a new question after the reader scrolled up', () => {
    useChatStore.setState({
      messages: [
        { id: 'user-1', role: 'user', content: '旧问题' },
        { id: 'assistant-1', role: 'assistant', content: '旧回答' },
      ],
    })
    render(<ChatSection />)
    const scroller = screen.getByTestId('chat-message-scroll')
    Object.defineProperties(scroller, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    })

    fireEvent.scroll(scroller)
    act(() => {
      useChatStore.setState((state) => ({
        messages: [
          ...state.messages,
          { id: 'user-2', role: 'user', content: '新问题' },
          { id: 'assistant-2', role: 'assistant', content: '', streaming: true },
        ],
      }))
    })

    expect(scroller.scrollTop).toBe(1000)
  })

  it('renders an accessible stable clear icon button', () => {
    render(<ChatSection />)

    const clear = screen.getByRole('button', { name: '清空对话' })
    expect(clear).toHaveAttribute('title', '清空对话')
    expect(clear).toHaveClass('chat-section__clear')
    expect(clear).toBeDisabled()
  })

  it('requires confirmation before clearing a nonempty conversation', () => {
    const clear = vi.fn(async () => undefined)
    const confirm = vi.spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true)
    useChatStore.setState({
      messages: [{ id: 'user-1', role: 'user', content: '测试问题' }],
      clear,
    })
    render(<ChatSection />)
    const clearButton = screen.getByRole('button', { name: '清空对话' })

    expect(clearButton).toBeEnabled()
    fireEvent.click(clearButton)
    expect(clear).not.toHaveBeenCalled()
    fireEvent.click(clearButton)

    expect(confirm).toHaveBeenCalledTimes(2)
    expect(clear).toHaveBeenCalledTimes(1)
    confirm.mockRestore()
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
