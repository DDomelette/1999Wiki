import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { WikiErrorBoundary } from './WikiErrorBoundary'

function Broken({ fail }: { fail: boolean }) {
  if (fail) throw new Error('render failure')
  return <p>内容恢复</p>
}

function Harness() {
  const [fail, setFail] = useState(true)
  return (
    <>
      <button type="button" onClick={() => setFail(false)}>切换页面</button>
      <WikiErrorBoundary resetKey={String(fail)} fallback={<p>局部渲染失败</p>}>
        <Broken fail={fail} />
      </WikiErrorBoundary>
    </>
  )
}

describe('WikiErrorBoundary', () => {
  it('contains a render failure and resets when resetKey changes', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    try {
      render(<Harness />)

      expect(screen.getByText('局部渲染失败')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: '切换页面' }))
      expect(screen.getByText('内容恢复')).toBeInTheDocument()
    } finally {
      consoleError.mockRestore()
    }
  })
})
