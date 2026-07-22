import { Archive, BookOpen, LayoutDashboard, Swords } from 'lucide-react'
import { useRef } from 'react'
import { CharacterCollection } from '../wiki/character-detail/CharacterCollection'
import { CharacterCulture } from '../wiki/character-detail/CharacterCulture'
import {
  CharacterProfileData,
  CharacterProgression,
  CharacterSummary,
  CharacterTechnicalFooter,
} from '../wiki/character-detail/CharacterDossierBlocks'
import { CharacterSkillCards } from '../wiki/character-detail/CharacterSkillCards'
import { CharacterVoiceRecords } from '../wiki/character-detail/CharacterVoiceRecords'
import { KimiCharacterStage } from './KimiCharacterStage'
import type { KimiWikiDetailViewModel } from './kimiWikiPreviewViewModel'

export function KimiMobileCharacterDossier({
  model,
  onBack,
}: {
  model: KimiWikiDetailViewModel
  onBack(): void
}) {
  const { character } = model
  const combatRef = useRef<HTMLElement>(null)

  return (
    <article className="kimi-mobile-character-dossier" data-testid="kimi-mobile-character-dossier">
      <section data-mobile-module="hero">
        <KimiCharacterStage model={model} mode="mobile" />
      </section>
      <section data-mobile-module="summary">
        <CharacterSummary viewModel={character} />
      </section>
      <section data-mobile-module="profile">
        <CharacterProfileData viewModel={character} />
      </section>
      {character.inheritance ? (
        <section data-mobile-module="inheritance">
          <CharacterProgression id="inheritance" title="传承" progression={character.inheritance} />
        </section>
      ) : null}
      {character.portray ? (
        <section data-mobile-module="portray">
          <CharacterProgression id="portray" title="塑造" progression={character.portray} />
        </section>
      ) : null}
      {character.skills.some((item) => item.kind === 'skill') ? (
        <section ref={combatRef} id="combat" data-mobile-module="skills">
          <CharacterSkillCards skills={character.skills} kind="skill" />
        </section>
      ) : null}
      {character.skills.some((item) => item.kind === 'ultimate') ? (
        <section data-mobile-module="ultimate">
          <CharacterSkillCards skills={character.skills} kind="ultimate" />
        </section>
      ) : null}
      {character.voices.length > 0 ? (
        <section data-mobile-module="voices">
          <CharacterVoiceRecords voices={character.voices} />
        </section>
      ) : null}
      {character.cultureEntries.length > 0 ? (
        <section data-mobile-module="culture">
          <CharacterCulture entries={character.cultureEntries} />
        </section>
      ) : null}
      {character.collectionGroups.length > 0 ? (
        <section data-mobile-module="collection">
          <CharacterCollection groups={character.collectionGroups} />
        </section>
      ) : null}
      <section data-mobile-module="technical">
        <CharacterTechnicalFooter viewModel={character} />
      </section>

      <nav className="kimi-mobile-dossier-tabs" aria-label="移动档案导航">
        <button type="button" aria-current="page">
          <LayoutDashboard aria-hidden="true" />
          <span>DOSSIER</span>
        </button>
        <button type="button" onClick={onBack}>
          <Archive aria-hidden="true" />
          <span>ARCHIVE</span>
        </button>
        <button
          type="button"
          onClick={() => combatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        >
          <Swords aria-hidden="true" />
          <span>COMBAT</span>
        </button>
        <span className="kimi-mobile-dossier-tabs__status"><BookOpen aria-hidden="true" /></span>
      </nav>
    </article>
  )
}
