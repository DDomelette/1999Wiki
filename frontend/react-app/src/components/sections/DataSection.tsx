import { useUIStore } from '../../store/uiStore'
import { CategoryPanel } from './CategoryPanel'

export function DataSection() {
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)
  const currentCategory = useUIStore((s) => s.currentCategory)

  return (
    <section
      data-snap-section="data"
      className="snap-section"
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      {/* 内嵌 6 板块的滚动容器 */}
      <div
        className="native-scrollbar-hidden"
        data-testid="data-section-scroll"
        style={{
          height: '100%',
          overflowY: 'scroll',
          scrollSnapType: 'y mandatory',
          scrollBehavior: 'smooth',
        }}
      >
        {categoriesMeta.map((c) => (
          <CategoryPanel key={c.key} meta={c} />
        ))}
      </div>

      {/* 左侧固定板块导航 */}
      <nav
        style={{
          position: 'absolute', left: 24, top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 5,
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        {categoriesMeta.map((c) => (
          <button
            key={c.key}
            onClick={() => {
              const el = document.querySelector(`[data-snap-section="data:${c.key}"]`)
              el?.scrollIntoView({ behavior: 'smooth' })
            }}
            style={{
              padding: '6px 12px',
              color: currentCategory === c.key ? 'var(--accent-gold)' : 'var(--text-muted)',
              borderLeft: currentCategory === c.key ? '2px solid var(--accent-gold)' : '2px solid transparent',
              fontFamily: 'var(--font-body)',
              fontSize: '0.9rem',
              transition: 'color 0.2s, border-color 0.2s',
              textAlign: 'left',
            }}
          >
            {c.title}
          </button>
        ))}
      </nav>
    </section>
  )
}
