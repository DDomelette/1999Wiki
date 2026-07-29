import { useUIStore } from '../../store/uiStore'
import { navigateToMainSection } from '../../navigation/mainSectionNavigation'
import { CategoryPanel } from './CategoryPanel'
import './DataSection.css'

export function DataSection() {
  const categoriesMeta = useUIStore((s) => s.categoriesMeta)
  const currentCategory = useUIStore((s) => s.currentCategory)

  return (
    <section className="data-section" data-main-data-sequence>
      {/* 覆盖整个资料序列的粘性分类导航 */}
      <div className="data-section__nav-shell">
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
                  const behavior: ScrollBehavior =
                    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
                      ? 'auto'
                      : 'smooth'
                  navigateToMainSection({ kind: 'data', categoryKey: c.key }, { behavior, history: 'push' })
                }}
              >
                {c.title}
              </button>
            )
          })}
        </nav>
      </div>

      {/* 资料分类直接作为主容器的吸附叶目标,不再拥有独立纵向滚动 */}
      <div
        className="native-scrollbar-hidden data-section__panels"
        data-testid="data-section-scroll"
      >
        {categoriesMeta.length === 0 ? (
          <section
            className="snap-section category-panel data-section__loading-panel"
            data-snap-section="data:loading"
            aria-label="资料加载中"
          >
            <p>资料加载中…</p>
          </section>
        ) : (
          categoriesMeta.map((c) => <CategoryPanel key={c.key} meta={c} />)
        )}
      </div>
    </section>
  )
}
