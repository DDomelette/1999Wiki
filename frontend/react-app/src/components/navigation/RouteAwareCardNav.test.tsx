import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RouteAwareCardNav } from './RouteAwareCardNav'
import { useUIStore } from '../../store/uiStore'

describe('RouteAwareCardNav', () => {
  beforeEach(() => useUIStore.getState().setTopNav(true))
  afterEach(() => {
    document.querySelectorAll('.snap-container').forEach((el) => el.remove())
    window.history.pushState({}, '', '/')
    vi.restoreAllMocks()
  })
  it('renders route-specific primary actions and three menu groups', async () => {
    const { rerender } = render(<RouteAwareCardNav mode="main" />)
    expect(screen.getByRole('link', { name: 'WIKI' })).toHaveAttribute('href', '/wiki/character')
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    expect(screen.getAllByTestId('card-nav-group')).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: '收起导航' }))
    // 关闭动画播放完后菜单才会卸载
    await waitFor(() => expect(screen.queryByTestId('card-nav-menu')).not.toBeInTheDocument())

    rerender(<RouteAwareCardNav mode="wiki" categories={[
      { key: 'character', label: '角色', count: 30 },
      { key: 'story', label: '剧情', count: 12 },
    ]} />)
    expect(screen.getByRole('link', { name: '首页' })).toHaveAttribute('href', '/')
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    expect(screen.getByRole('button', { name: '角色 30' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '剧情 12' })).toBeEnabled()
  })

  it('uses dynamic wiki categories and closes with Escape', async () => {
    const onSelect = vi.fn()
    render(<RouteAwareCardNav mode="wiki" categories={[{ key: 'story', label: '剧情', count: 12 }]} onCategorySelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    fireEvent.click(screen.getByRole('button', { name: '剧情 12' }))
    expect(onSelect).toHaveBeenCalledWith('story')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('card-nav-menu')).not.toBeInTheDocument())
  })

  it('places the theme toggle immediately before the primary action', () => {
    render(<RouteAwareCardNav mode="main" />)
    const primary = screen.getByRole('link', { name: 'WIKI' })
    expect(primary.previousElementSibling).toHaveClass('theme-toggle')
  })

  it('renders a visible back button when onBack is provided and calls it on click', () => {
    const onBack = vi.fn()
    render(<RouteAwareCardNav mode="wiki" onBack={onBack} />)
    const back = screen.getByRole('button', { name: '返回' })
    expect(back).toBeVisible()
    fireEvent.click(back)
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('places controls in back → theme → primary order when onBack is provided', () => {
    render(<RouteAwareCardNav mode="wiki" onBack={vi.fn()} />)
    const actions = screen.getByRole('navigation', { name: '全局导航' }).querySelector('.card-nav__actions')
    const children = [...actions!.children]
    expect(children[0]).toHaveClass('card-nav__back')
    expect(children[1]).toHaveClass('theme-toggle')
    expect(children[2]).toHaveClass('card-nav__primary')
  })

  it('marks one archival navigation context without restoring a category rail', () => {
    render(<RouteAwareCardNav mode="wiki" pageType="character" />)

    expect(screen.getByRole('navigation', { name: '全局导航' })).toHaveClass('card-nav--archive', 'card-nav--wiki')
    expect(screen.getByRole('navigation', { name: '全局导航' })).toHaveAttribute('data-nav-context', 'character')
    expect(document.querySelector('[data-testid="wiki-category-rail"]')).toBeNull()
    expect(document.querySelector('aside.sidebar')).toBeNull()
  })

  it('keeps the menu visible and operable with reduced motion', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    const onSelect = vi.fn()
    render(<RouteAwareCardNav mode="wiki" categories={[{ key: 'character', label: '角色', count: 30 }]} onCategorySelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    expect(screen.getByTestId('card-nav-menu')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '角色 30' }))
    expect(onSelect).toHaveBeenCalledWith('character')
  })

  it('keeps the Wiki 问答 link pointing at /#chat', () => {
    render(<RouteAwareCardNav mode="wiki" categories={[{ key: 'character', label: '角色', count: 30 }]} />)
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    expect(screen.getByRole('link', { name: '问答' })).toHaveAttribute('href', '/#chat')
  })

  it('routes the main 问答 action through the shared scroller, pushes history, and closes the menu', async () => {
    const scroller = document.createElement('main')
    scroller.className = 'snap-container'
    for (const id of ['home', 'data:人物', 'chat']) {
      const section = document.createElement('section')
      section.setAttribute('data-snap-section', id)
      scroller.appendChild(section)
    }
    document.body.appendChild(scroller)
    scroller.getBoundingClientRect = () => ({ top: 0 }) as DOMRect
    const chat = [...scroller.querySelectorAll<HTMLElement>('[data-snap-section]')]
      .find((el) => el.getAttribute('data-snap-section') === 'chat')!
    chat.getBoundingClientRect = () => ({ top: 500 }) as DOMRect
    const scrollTo = vi.fn()
    scroller.scrollTo = scrollTo
    const pushState = vi.spyOn(window.history, 'pushState')

    render(<RouteAwareCardNav mode="main" />)
    fireEvent.click(screen.getByRole('button', { name: '展开导航' }))
    fireEvent.click(screen.getByRole('button', { name: '问答' }))

    expect(scrollTo).toHaveBeenCalledWith({ top: 500, behavior: 'smooth' })
    expect(pushState).toHaveBeenCalledWith({}, '', '/#chat')
    await waitFor(() => expect(screen.queryByTestId('card-nav-menu')).not.toBeInTheDocument())
  })
})
