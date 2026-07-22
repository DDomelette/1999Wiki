import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { VoiceLineGroup } from '../../types'
import { AnimatedVoiceList } from './AnimatedVoiceList'

const lines: VoiceLineGroup[] = [
  { voice_line_id: 'first', title: '初见', variants: [] },
  { voice_line_id: 'second', title: '问候', variants: [] },
]

describe('AnimatedVoiceList', () => {
  it('delegates every line to a replayable list while the panel owns the visible scrollbar', () => {
    render(<AnimatedVoiceList lines={lines} renderLine={(line) => <button type="button">{line.title}</button>} />)

    const list = screen.getByRole('listbox', { name: 'Voice lines' })
    expect(list).toHaveClass('reactbits-animated-list', 'voice-animated-list')
    expect(list).not.toHaveClass('reactbits-scrollbar-hidden')
    expect(list).toHaveAttribute('data-replay-on-enter', 'true')
    expect(screen.getAllByRole('option')).toHaveLength(lines.length)
    expect(screen.getByRole('button', { name: '初见' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '问候' })).toBeInTheDocument()
  })

  it('keeps arrow focus movement scoped to the voice list', () => {
    render(<AnimatedVoiceList lines={lines} renderLine={(line) => <span>{line.title}</span>} />)
    const list = screen.getByRole('listbox', { name: 'Voice lines' })
    const options = screen.getAllByRole('option')

    expect(options[0]).toHaveAttribute('data-active', 'true')
    fireEvent.keyDown(list, { key: 'ArrowDown' })
    expect(options[1]).toHaveAttribute('data-active', 'true')
  })
})
