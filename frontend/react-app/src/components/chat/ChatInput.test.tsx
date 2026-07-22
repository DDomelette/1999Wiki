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
})
