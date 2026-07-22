import { Archive, BookOpen, LayoutDashboard, Swords } from 'lucide-react'
import { useRef } from 'react'
import type { CharacterDetailViewModel } from '../characterDetailViewModel'
import { CharacterCollection } from './CharacterCollection'
import { CharacterCulture } from './CharacterCulture'
import {
  CharacterProfileData,
  CharacterProgression,
  CharacterSummary,
  CharacterTechnicalFooter,
} from './CharacterDossierBlocks'
import { CharacterPortraitStage } from './CharacterPortraitStage'
import { CharacterSkillCards } from './CharacterSkillCards'
import { CharacterVoiceRecords } from './CharacterVoiceRecords'

export function MobileCharacterDossier({
  viewModel,
  onBack,
}: {
  viewModel: CharacterDetailViewModel
  onBack(): void
}) {
  const combatRef = useRef<HTMLElement>(null)
  const scrollToCombat = () => combatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <article className="mobile-character-dossier" data-testid="mobile-character-dossier">
      <section className="mobile-character-dossier__hero" data-mobile-module="hero">
        <CharacterPortraitStage viewModel={viewModel} mode="mobile" />
      </section>
      <section className="mobile-character-dossier__summary" data-mobile-module="summary">
        <CharacterSummary viewModel={viewModel} />
      </section>
      <section className="mobile-character-dossier__profile" data-mobile-module="profile">
        <CharacterProfileData viewModel={viewModel} />
      </section>
      {viewModel.inheritance ? (
        <section className="mobile-character-dossier__inheritance" data-mobile-module="inheritance">
          <CharacterProgression id="inheritance" title="传承" progression={viewModel.inheritance} />
        </section>
      ) : null}
      {viewModel.portray ? (
        <section className="mobile-character-dossier__portray" data-mobile-module="portray">
          <CharacterProgression id="portray" title="塑造" progression={viewModel.portray} />
        </section>
      ) : null}
      {viewModel.skills.some((item) => item.kind === 'skill') ? (
        <section ref={combatRef} id="combat" className="mobile-character-dossier__skills" data-mobile-module="skills">
          <CharacterSkillCards skills={viewModel.skills} kind="skill" />
        </section>
      ) : null}
      {viewModel.skills.some((item) => item.kind === 'ultimate') ? (
        <section className="mobile-character-dossier__ultimate" data-mobile-module="ultimate">
          <CharacterSkillCards skills={viewModel.skills} kind="ultimate" />
        </section>
      ) : null}
      {viewModel.voices.length > 0 ? (
        <section className="mobile-character-dossier__voices" data-mobile-module="voices">
          <CharacterVoiceRecords voices={viewModel.voices} />
        </section>
      ) : null}
      {viewModel.cultureEntries.length > 0 ? (
        <section className="mobile-character-dossier__culture" data-mobile-module="culture">
          <CharacterCulture entries={viewModel.cultureEntries} />
        </section>
      ) : null}
      {viewModel.collectionGroups.length > 0 ? (
        <section className="mobile-character-dossier__collection" data-mobile-module="collection">
          <CharacterCollection groups={viewModel.collectionGroups} />
        </section>
      ) : null}
      <section className="mobile-character-dossier__technical" data-mobile-module="technical">
        <CharacterTechnicalFooter viewModel={viewModel} />
      </section>

      <nav className="mobile-dossier-tabs" aria-label="移动档案导航">
        <button type="button" aria-current="page">
          <LayoutDashboard aria-hidden="true" />
          <span>DOSSIER</span>
        </button>
        <button type="button" onClick={onBack}>
          <Archive aria-hidden="true" />
          <span>ARCHIVE</span>
        </button>
        <button type="button" onClick={scrollToCombat}>
          <Swords aria-hidden="true" />
          <span>COMBAT</span>
        </button>
        <span className="mobile-dossier-tabs__status">
          <BookOpen aria-hidden="true" />
        </span>
      </nav>
    </article>
  )
}
