import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import gsap from 'gsap'
import './CardNav.css'

export interface CardNavLink {
  label: string
  href?: string
  action?: () => void
  disabled?: boolean
}

export interface CardNavGroup {
  label: string
  links: CardNavLink[]
}

export interface CardNavProps {
  groups: CardNavGroup[]
  open: boolean
  onOpenChange: (open: boolean) => void
  primary: ReactNode
  themeControl: ReactNode
  backControl?: ReactNode
  visible?: boolean
  context?: string
  className?: string
  dataContext?: string
}

export function CardNav({ groups, open, onOpenChange, primary, themeControl, backControl, visible = true, context = '', className = '', dataContext = '' }: CardNavProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  // 菜单在关闭动画播放完之前保持挂载
  const [menuMounted, setMenuMounted] = useState(open)

  useEffect(() => {
    if (open) setMenuMounted(true)
  }, [open])

  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === 'Escape' && onOpenChange(false)
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onOpenChange])

  useEffect(() => {
    const menu = menuRef.current
    if (!menu) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      if (!open) setMenuMounted(false)
      gsap.set(menu, { opacity: 1, y: 0 })
      return
    }
    if (open) {
      // 展开：线性位移 + 从快到慢的阻尼感（power2.out，无回弹）
      const context = gsap.context(() => gsap.fromTo(menu, { opacity: 0, y: -14 }, { opacity: 1, y: 0, duration: 0.3, ease: 'power2.out' }), menuRef)
      return () => context.revert()
    }
    // 收回：同样的阻尼曲线，动画结束后卸载菜单
    const tween = gsap.to(menu, { opacity: 0, y: -14, duration: 0.24, ease: 'power2.out', onComplete: () => setMenuMounted(false) })
    return () => { tween.kill() }
  }, [open, menuMounted])

  if (!visible) return null
  return (
    <nav
      className={`card-nav ${className}`.trim()}
      aria-label="全局导航"
      data-nav-context={dataContext || undefined}
      onMouseLeave={() => { if (open) onOpenChange(false) }}
    >
      <div className="card-nav__bar">
        <button type="button" className="card-nav__toggle" onClick={() => onOpenChange(!open)} aria-expanded={open} aria-label={open ? '收起导航' : '展开导航'}>
          {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
        <span className="card-nav__brand">REVERSE 1999</span>
        <div className="card-nav__actions">{backControl}{themeControl}{primary}</div>
      </div>
      {menuMounted && (
        <div ref={menuRef} className="card-nav__menu" data-testid="card-nav-menu" data-page-type={context || undefined}>
          {groups.map((group) => (
            <section key={group.label} className="card-nav__group" data-testid="card-nav-group">
              <h2>{group.label}</h2>
              {group.links.map((link) => link.href ? (
                <a key={link.label} href={link.href} aria-disabled={link.disabled || undefined} onClick={(event) => link.disabled && event.preventDefault()}>{link.label}</a>
              ) : (
                <button key={link.label} type="button" disabled={link.disabled} onClick={() => { link.action?.(); onOpenChange(false) }}>{link.label}</button>
              ))}
            </section>
          ))}
        </div>
      )}
    </nav>
  )
}
