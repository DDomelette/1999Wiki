import { BadgeInfo, FileCheck2, MapPin } from 'lucide-react'
import type {
  CharacterDetailViewModel,
  CharacterProgressionViewModel,
} from '../characterDetailViewModel'

export function CharacterIdentityCard({ viewModel }: { viewModel: CharacterDetailViewModel }) {
  const portrait = viewModel.portraitStates.find((item) => item.variant === 'initial')
    ?? viewModel.portraitStates[0]
  const portraitMedia = portrait?.portraitMedia ?? portrait?.live2dMedia
  return (
    <header className="character-identity-card">
      {portraitMedia ? (
        <img
          className="character-identity-card__portrait"
          src={portraitMedia.url}
          alt=""
          data-testid="character-identity-portrait"
        />
      ) : null}
      <div className="character-identity-card__copy">
        <p className="character-detail__eyebrow">SUBJECT_EXONYM</p>
        <h1>{viewModel.identity.exonym || viewModel.identity.name}</h1>
        {viewModel.identity.exonym ? <p className="character-identity-card__name">{viewModel.identity.name}</p> : null}
        <div className="character-identity-card__tags">
          {viewModel.summaryCards.find((item) => item.key === 'inspiration') ? (
            <span>{viewModel.summaryCards.find((item) => item.key === 'inspiration')?.value}</span>
          ) : null}
          {viewModel.profileRows.find((item) => item.key === 'stars') ? (
            <span>{viewModel.profileRows.find((item) => item.key === 'stars')?.value}</span>
          ) : null}
        </div>
      </div>
    </header>
  )
}

export function CharacterSummary({ viewModel }: { viewModel: CharacterDetailViewModel }) {
  return (
    <section className="character-summary" aria-labelledby="character-summary-title">
      <div className="character-summary__cards">
        {viewModel.summaryCards.map((card) => (
          <article className={`character-summary-card character-summary-card--${card.key}`} key={card.key}>
            <p>{card.label}</p>
            <strong>{card.value}</strong>
            {card.detail ? <small>{card.detail}</small> : null}
          </article>
        ))}
      </div>
      {viewModel.location ? (
        <div className="character-location-trace">
          <MapPin aria-hidden="true" />
          <div>
            <p>LOCATION_TRACE</p>
            <strong>{viewModel.location}</strong>
          </div>
        </div>
      ) : null}
      <div className="character-summary__copy">
        <p className="character-detail__eyebrow" id="character-summary-title">CHARACTER_LORE / 概述</p>
        <p>{viewModel.summary}</p>
        {viewModel.quote ? <blockquote>{viewModel.quote}</blockquote> : null}
      </div>
      {viewModel.udimoMedia ? (
        <figure className="character-summary__udimo" data-testid="character-udimo-archive">
          <img
            src={viewModel.udimoMedia.url}
            alt={viewModel.udimoMedia.title}
            data-testid="character-udimo-media"
          />
          <figcaption>
            <span>UDIMO_ARCHIVE</span>
            <strong>{viewModel.profileRows.find((row) => row.key === 'udimo')?.value || 'Udimo'}</strong>
          </figcaption>
          <dl className="character-summary__udimo-metadata">
            <div>
              <dt>ACTIVE_ERA</dt>
              <dd>{viewModel.archiveMetadata.activeEra || 'UNKNOWN'}</dd>
            </div>
            <div>
              <dt>BIRTHDAY</dt>
              <dd>{viewModel.archiveMetadata.birthday || 'UNKNOWN'}</dd>
            </div>
          </dl>
        </figure>
      ) : null}
    </section>
  )
}

export function CharacterProfileData({ viewModel }: { viewModel: CharacterDetailViewModel }) {
  if (viewModel.profileRows.length === 0) return null
  return (
    <section className="character-profile-data" aria-labelledby="profile-data-title">
      <span className="character-profile-data__tape" aria-hidden="true" />
      <span className="character-profile-data__stamp">VERIFIED</span>
      <h2 id="profile-data-title">PROFILE_DATA</h2>
      <dl>
        {viewModel.profileRows.map((row) => {
          const presentation = profilePaperPresentation(viewModel, row)
          return (
            <div data-profile-key={row.key} key={row.key}>
              <dt>{presentation.label}</dt>
              <dd>{presentation.value}</dd>
            </div>
          )
        })}
      </dl>
      {viewModel.quote ? <blockquote>{viewModel.quote}</blockquote> : null}
    </section>
  )
}

function profilePaperPresentation(
  viewModel: CharacterDetailViewModel,
  row: CharacterDetailViewModel['profileRows'][number],
): { label: string; value: string } {
  if (row.key === 'medium') {
    const mediumEnglish = row.value === '树木' ? 'Trees' : ''
    return { label: 'Medium:', value: mediumEnglish ? `${row.value} (${mediumEnglish})` : row.value }
  }
  if (row.key === 'damageType') {
    const damage = viewModel.summaryCards.find((item) => item.key === 'damageType')
    const detail = damage?.detail || ''
    const value = damage?.value || row.value
    return { label: 'Damage Type:', value: detail ? `${detail} (${value})` : value }
  }
  if (row.key === 'birthday') {
    const birthday = viewModel.archiveMetadata.birthday
    const match = birthday.match(/(?:Oct\s+)?(\d{1,2})\s*(?:\(([^)]+)\))?/i)
    const rawDate = row.value.match(/\d{4}-(\d{2})-(\d{2})/)
    const monthDay = rawDate ? `${rawDate[1]}-${rawDate[2]}` : row.value
    const season = match?.[2] || ''
    return { label: 'Birthday:', value: season ? `${monthDay} (${season})` : monthDay }
  }
  if (row.key === 'position') {
    return { label: 'Tags:', value: row.value.split(/\s+/).filter(Boolean).join(' / ') }
  }
  return { label: row.label, value: row.value }
}

export function CharacterProgression({
  id,
  title,
  progression,
}: {
  id: string
  title: string
  progression: CharacterProgressionViewModel | null
}) {
  if (!progression) return null
  return (
    <section className={`character-progression character-progression--${id}`} aria-labelledby={`${id}-title`}>
      <p className="character-detail__eyebrow">{id.toUpperCase()}</p>
      <h2 id={`${id}-title`}>{progression.title || title}</h2>
      {progression.description ? <p className="character-progression__description">{progression.description}</p> : null}
      <ol>
        {progression.levels.map((item) => (
          <li key={`${item.level}-${item.effect}`}>
            <span>{item.level}</span>
            <p>{item.effect}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function CharacterTechnicalFooter({ viewModel }: { viewModel: CharacterDetailViewModel }) {
  const dossier = viewModel.technicalDossier
  return (
    <footer className="character-technical-footer">
      <FileCheck2 aria-hidden="true" />
      <div>
        <p>TECHNICAL_DOSSIER</p>
        <span>{dossier.sourceTitle}</span>
        <span>{dossier.projectionVersion == null ? '' : `CRAWLER_PROJECTION_V${dossier.projectionVersion}`}</span>
        <span>{dossier.route}</span>
      </div>
      <BadgeInfo aria-hidden="true" />
    </footer>
  )
}
