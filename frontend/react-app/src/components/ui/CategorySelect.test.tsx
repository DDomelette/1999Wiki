import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { CategorySelect } from './CategorySelect'
import { useChatStore } from '../../store/chatStore'

describe('CategorySelect', () => {
  beforeEach(() => {
    useChatStore.setState({ category: null })
  })

  it('selects a category with the mouse and returns focus to the trigger', () => {
    render(<CategorySelect />)
    const trigger = screen.getByRole('combobox', { name: '检索范围' })

    fireEvent.click(trigger)
    expect(screen.getByRole('listbox')).toHaveFocus()
    expect(screen.getByRole('option', { name: '全部' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('option', { name: '人物' }))

    expect(useChatStore.getState().category).toBe('人物')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(trigger).toHaveTextContent('人物')
    expect(trigger).toHaveFocus()
  })

  it('supports keyboard navigation and selection', () => {
    render(<CategorySelect />)
    const trigger = screen.getByRole('combobox', { name: '检索范围' })

    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    const listbox = screen.getByRole('listbox')
    const lastOption = screen.getByRole('option', { name: '日历' })
    expect(listbox).toHaveFocus()
    expect(listbox).toHaveAttribute('data-page-wheel-lock', 'true')
    fireEvent.keyDown(listbox, { key: 'End' })

    expect(listbox).toHaveAttribute('aria-activedescendant', lastOption.id)
    expect(lastOption).toHaveAttribute('data-active', 'true')
    fireEvent.keyDown(listbox, { key: 'Enter' })
    expect(useChatStore.getState().category).toBe('日历')
    expect(trigger).toHaveTextContent('日历')
    expect(trigger).toHaveFocus()
  })

  it('scrolls the active option into view during keyboard navigation', () => {
    render(<CategorySelect />)
    fireEvent.click(screen.getByRole('combobox', { name: '检索范围' }))
    const listbox = screen.getByRole('listbox')
    Object.defineProperties(listbox, {
      clientHeight: { configurable: true, value: 100 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    })
    screen.getAllByRole('option').forEach((option, index) => {
      Object.defineProperties(option, {
        offsetTop: { configurable: true, value: index * 40 },
        offsetHeight: { configurable: true, value: 36 },
      })
    })

    fireEvent.keyDown(listbox, { key: 'End' })
    expect(listbox.scrollTop).toBe(176)
    fireEvent.keyDown(listbox, { key: 'Home' })
    expect(listbox.scrollTop).toBe(0)
  })

  it('closes with Escape without changing the selected category', () => {
    render(<CategorySelect />)
    const trigger = screen.getByRole('combobox', { name: '检索范围' })

    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' })

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(useChatStore.getState().category).toBeNull()
    expect(trigger).toHaveFocus()
  })

  it('closes on an outside pointer without changing the selected category', () => {
    render(<CategorySelect />)
    const trigger = screen.getByRole('combobox', { name: '检索范围' })

    fireEvent.click(trigger)
    fireEvent.pointerDown(document.body)

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(useChatStore.getState().category).toBeNull()
  })
})
