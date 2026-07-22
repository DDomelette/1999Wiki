import type { WikiPageViewModel } from './wikiViewModel'
import './PageInfo.css'

interface PageInfoProps {
  view: WikiPageViewModel | null
}

export function PageInfo({ view }: PageInfoProps) {
  return (
    <aside data-testid="wiki-page-info" id="wiki-info" className="wiki-dossier-info">
      <header className="wiki-dossier-info__header">
        <span className="archive-kicker">Traceable Record</span>
        <h2>PAGE INFO</h2>
      </header>

      {!view ? <p className="archive-empty">未选择页面</p> : (
        <>
          {view.profileFacts.length ? (
            <section className="wiki-dossier-info__section">
              <h3>角色事实</h3>
              <dl className="wiki-dossier-info__fields">
                {view.profileFacts.map((field) => (
                  <DossierField key={`profile-${field.label}`} label={field.label} value={field.value} />
                ))}
              </dl>
            </section>
          ) : null}

          <section className="wiki-dossier-info__section">
            <h3>追溯信息</h3>
            <dl className="wiki-dossier-info__fields">
              {view.dossier.map((field) => (
                <DossierField key={`dossier-${field.label}`} label={field.label} value={field.value} href={field.href} />
              ))}
            </dl>
          </section>

          {view.page.relations.length ? (
            <section className="wiki-dossier-info__section">
              <h3>关联页面</h3>
              <ul className="wiki-dossier-info__relations" aria-label="关联页面">
                {view.page.relations.map((relation, index) => {
                  const label = relationLabel(relation, index)
                  const route = relationRoute(relation)
                  return <li key={`${label}-${index}`}>{route ? <a href={route}>{label}</a> : label}</li>
                })}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </aside>
  )
}

function DossierField({ label, value, href }: { label: string; value: string; href?: string }) {
  const display = value.trim() || '无'
  return (
    <div>
      <dt>{label}</dt>
      <dd>{href ? <a href={href}>{display}</a> : display}</dd>
    </div>
  )
}

function relationLabel(relation: Record<string, unknown>, index: number): string {
  return firstString(
    relation.title,
    relation.targetTitle,
    relation.target_title,
    relation.label,
    relation.name,
    relation.text,
    relation.relationType,
    relation.relation_type,
  ) || `关系 ${index + 1}`
}

function relationRoute(relation: Record<string, unknown>): string {
  return firstString(relation.targetRoute, relation.target_route, relation.route)
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}
