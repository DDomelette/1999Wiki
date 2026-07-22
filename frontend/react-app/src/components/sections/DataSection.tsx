import { useUIStore } from '../../store/uiStore'
import { CategoryPanel } from './CategoryPanel'
import './DataSection.css'

export function DataSection() {
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)
  const currentCategory = useUIStore((s) => s.currentCategory)

  return (
    <section data-snap-section="data" className="snap-section data-section">
      {/* 内嵌 6 板块的滚动容器 */}
      <div
        className="native-scrollbar-hidden data-section__scroll"
        data-testid="data-section-scroll"
      >
        {categoriesMeta.map((c) => (
          <CategoryPanel key={c.key} meta={c} />
        ))}
      </div>

      {/* 左侧固定板块导航 */}
      <nav className="data-section__nav" aria-label="资料分类">
        {categoriesMeta.map((c) => {
          const isActive = currentCategory === c.key
          return (
            <button
              key={c.key}
              className="data-section__nav-button"
              data-active={isActive ? 'true' : undefined}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => {
                const el = document.querySelector(`[data-snap-section="data:${c.key}"]`)
                el?.scrollIntoView({ behavior: 'smooth' })
              }}
            >
              {c.title}
            </button>
          )
        })}
      </nav>
    </section>
  )
}
