import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatInput } from './ChatInput'
import { useChatStore } from '../../store/chatStore'

describe('ChatInput suggested questions', () => {
  const send = vi.fn(async (_question: string) => undefined)

  beforeEach(() => {
    send.mockClear()
    useChatStore.setState({
      messages: [],
      category: null,
      sending: false,
      abortController: null,
      routeOptions: { expanded: false, freeSupplement: false },
      send,
    })
  })

  it('replaces and focuses the draft without sending when a suggestion is selected', () => {
    render(<ChatInput />)
    const input = screen.getByPlaceholderText('输入问题...')
    const suggestion = within(screen.getByRole('group', { name: '推荐问题' }))
      .getAllByRole('button')[0]
    const question = suggestion.textContent

    fireEvent.change(input, { target: { value: '尚未发送的草稿' } })
    fireEvent.click(suggestion)

    expect(input).toHaveValue(question)
    expect(input).toHaveFocus()
    expect(send).not.toHaveBeenCalled()
    expect(useChatStore.getState().messages).toEqual([])
  })

  it('keeps the mounted suggestion group stable when the draft changes', () => {
    render(<ChatInput />)
    const group = screen.getByRole('group', { name: '推荐问题' })
    const before = within(group).getAllByRole('button').map((button) => button.textContent)

    fireEvent.change(screen.getByPlaceholderText('输入问题...'), {
      target: { value: '修改草稿触发重渲染' },
    })

    const after = within(group).getAllByRole('button').map((button) => button.textContent)
    expect(after).toEqual(before)
  })

  it('disables suggestions while a message is sending', () => {
    useChatStore.setState({ sending: true })
    render(<ChatInput />)

    const buttons = within(screen.getByRole('group', { name: '推荐问题' }))
      .getAllByRole('button')
    expect(buttons).toHaveLength(4)
    for (const button of buttons) expect(button).toBeDisabled()
  })

  it('exposes a shrinkable input row and stable action hooks', () => {
    const { container } = render(<ChatInput />)

    expect(container.querySelector('.chat-input')).toBeInTheDocument()
    expect(container.querySelector('.chat-input__row')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '输入问题' })).toHaveClass('chat-input__field')
    expect(container.querySelector('button[type="submit"]')).toHaveClass('chat-input__send')
    expect(container.querySelector('.chat-input__modes')).toBeInTheDocument()
  })

  it('offers a stop action while generation is in progress', () => {
    const abort = vi.fn()
    useChatStore.setState({ sending: true, abort })
    render(<ChatInput />)

    const stop = screen.getByRole('button', { name: '停止' })
    expect(stop).toHaveAttribute('type', 'button')
    fireEvent.click(stop)

    expect(abort).toHaveBeenCalledOnce()
  })

  it('offers retry feedback when a partial answer fails validation', async () => {
    send.mockImplementationOnce(async () => {
      useChatStore.setState({
        messages: [
          { id: 'user-partial', role: 'user', content: 'question' },
          { id: 'assistant-partial', role: 'assistant', content: 'partial', phase: 'failed', partialError: true },
        ],
      })
    })
    render(<ChatInput />)

    fireEvent.change(screen.getByRole('textbox', { name: '输入问题' }), { target: { value: 'question' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('回答未完成，未经过引用校验。')
    expect(screen.getByRole('button', { name: '重试' })).toBeEnabled()
  })
})
