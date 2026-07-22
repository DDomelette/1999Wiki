import type { CharacterCultureEntryViewModel } from '../characterDetailViewModel'

export function CharacterCulture({ entries }: { entries: CharacterCultureEntryViewModel[] }) {
  if (entries.length === 0) return null
  return (
    <section className="character-culture" aria-labelledby="character-culture-title">
      <header>
        <p className="character-detail__eyebrow">CULTURE_ARCHIVE</p>
        <h2 id="character-culture-title">文化档案</h2>
      </header>
      {entries.map((entry) => (
        <article className="character-culture-entry" key={entry.id}>
          <span>{String(entry.ordinal).padStart(2, '0')}</span>
          <h3>{entry.title}</h3>
          {entry.titleEn ? <p className="character-culture-entry__english">{entry.titleEn}</p> : null}
          {entry.tags.length > 0 ? <p className="character-culture-entry__tags">{entry.tags.join(' / ')}</p> : null}
          {entry.paragraphs.map((paragraph, index) => <p key={`${entry.id}-${index}`}>{paragraph}</p>)}
        </article>
      ))}
    </section>
  )
}
