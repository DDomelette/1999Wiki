import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WikiCharacterSelectionPage } from './WikiCharacterSelectionPage'

describe('WikiCharacterSelectionPage', () => {
  it('contains only index, preview, summary and the detail CTA', () => {
    const onOpenDetail = vi.fn()
    render(
      <WikiCharacterSelectionPage
        index={<p>角色索引</p>}
        preview={<p>角色预览</p>}
        summary={<p>角色摘要</p>}
        canOpenDetail
        onOpenDetail={onOpenDetail}
      />,
    )

    expect(screen.getByTestId('wiki-character-selection')).toBeInTheDocument()
    expect(screen.getByTestId('selection-index')).toHaveTextContent('角色索引')
    expect(screen.getByTestId('selection-preview')).toHaveTextContent('角色预览')
    expect(screen.getByTestId('selection-summary')).toHaveTextContent('角色摘要')
    expect(screen.queryByTestId('wiki-character-detail')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wiki-structured-body')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '查看完整档案' }))
    expect(onOpenDetail).toHaveBeenCalledTimes(1)
  })

  it('disables the CTA when no stable route is available', () => {
    render(
      <WikiCharacterSelectionPage
        index={null}
        preview={null}
        summary={null}
        canOpenDetail={false}
        onOpenDetail={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: '查看完整档案' })).toBeDisabled()
  })
})
