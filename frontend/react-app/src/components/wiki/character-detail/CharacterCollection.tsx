import type { CharacterCollectionGroupViewModel } from '../characterDetailViewModel'

export function CharacterCollection({ groups }: { groups: CharacterCollectionGroupViewModel[] }) {
  if (groups.length === 0) return null
  return (
    <section className="character-collection" aria-labelledby="character-collection-title">
      <header>
        <p className="character-detail__eyebrow">COLLECTION</p>
        <h2 id="character-collection-title">藏品</h2>
      </header>
      {groups.map((group) => (
        <section className="character-collection-group" key={group.id}>
          <header>
            <h3>{group.name}</h3>
            {group.nameEn ? <p>{group.nameEn}</p> : null}
          </header>
          <div className="character-collection-group__items">
            {group.items.map((item) => (
              <article className="character-collection-item" data-testid="character-collection-item" key={item.id}>
                {item.image ? <img src={item.image.url} alt={item.name} /> : null}
                <div>
                  <p className="character-detail__eyebrow">ITEM_{String(item.ordinal).padStart(2, '0')}</p>
                  <h4>{item.name}</h4>
                  {item.nameEn ? <p className="character-collection-item__english">{item.nameEn}</p> : null}
                  {item.value ? <strong>{item.value}</strong> : null}
                  {item.description ? <p>{item.description}</p> : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </section>
  )
}
