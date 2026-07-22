import type { CharacterSkillViewModel } from '../characterDetailViewModel'

export function CharacterSkillCards({
  skills,
  kind = 'all',
}: {
  skills: CharacterSkillViewModel[]
  kind?: 'all' | 'skill' | 'ultimate'
}) {
  const visible = kind === 'all' ? skills : skills.filter((item) => item.kind === kind)
  if (visible.length === 0) return null
  return (
    <section className={`character-skill-cards character-skill-cards--${kind}`} aria-label={kind === 'ultimate' ? '至终仪式' : '技能档案'}>
      {visible.map((skill) => (
        <article
          className={`character-skill-card character-skill-card--${skill.kind}`}
          data-testid="character-skill-card"
          key={skill.id}
        >
          {skill.image ? <img src={skill.image.url} alt="" /> : null}
          <div className="character-skill-card__body">
            <p className="character-detail__eyebrow">{skill.kind === 'ultimate' ? 'ULTIMATE' : 'TACTICAL_SKILL'}</p>
            <h3>{skill.name}</h3>
            {skill.description ? <p>{skill.description}</p> : null}
            {skill.levels.length > 0 ? (
              <ol className="character-skill-card__levels">
                {skill.levels.map((level) => (
                  <li key={`${skill.id}-${level.level}`}>
                    <span>{level.level}</span>
                    <p>{level.effect}</p>
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
          <span className="character-skill-card__kind">{skill.kind === 'ultimate' ? 'ULTIMATE' : 'ATTACK'}</span>
        </article>
      ))}
    </section>
  )
}
