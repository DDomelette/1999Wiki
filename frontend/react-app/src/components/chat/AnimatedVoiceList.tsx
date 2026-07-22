import type { ReactNode } from 'react'
import type { VoiceLineGroup } from '../../types'
import { AnimatedList } from '../animations/reactbits/AnimatedList'

export function AnimatedVoiceList({ lines, renderLine }: { lines: readonly VoiceLineGroup[]; renderLine: (line: VoiceLineGroup) => ReactNode }) {
  return (
    <AnimatedList
      items={lines}
      itemKey={(line) => line.voice_line_id}
      renderItem={renderLine}
      displayScrollbar
      replayOnEnter
      ariaLabel="Voice lines"
      className="voice-animated-list"
    />
  )
}
