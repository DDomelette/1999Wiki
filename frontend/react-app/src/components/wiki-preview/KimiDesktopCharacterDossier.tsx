import { Archive, Database, FolderArchive, Swords } from 'lucide-react'
import { CharacterCollection } from '../wiki/character-detail/CharacterCollection'
import { CharacterCulture } from '../wiki/character-detail/CharacterCulture'
import {
  CharacterIdentityCard,
  CharacterProfileData,
  CharacterProgression,
  CharacterSummary,
  CharacterTechnicalFooter,
} from '../wiki/character-detail/CharacterDossierBlocks'
import { CharacterSkillCards } from '../wiki/character-detail/CharacterSkillCards'
import { CharacterVoiceRecords } from '../wiki/character-detail/CharacterVoiceRecords'
import { KimiCharacterStage } from './KimiCharacterStage'
import type { KimiWikiDetailViewModel } from './kimiWikiPreviewViewModel'

export function KimiDesktopCharacterDossier({
  model,
  onBack,
}: {
  model: KimiWikiDetailViewModel
  onBack(): void
}) {
  const { character } = model

  return (
    <article className="kimi-desktop-character-dossier" data-testid="kimi-desktop-character-dossier">
      <aside
        className="kimi-desktop-character-dossier__left native-scrollbar-hidden"
        data-scroll-owner="profile-skill-rail"
        tabIndex={0}
      >
        <CharacterIdentityCard viewModel={character} />
        <CharacterProfileData viewModel={character} />
        <div id="combat">
          <CharacterSkillCards skills={character.skills} />
        </div>
        <CharacterCulture entries={character.cultureEntries} />
        <nav className="kimi-desktop-character-dossier__utility" aria-label="详情页快捷操作">
          <button type="button" onClick={onBack} aria-label="返回角色索引">
            <Archive aria-hidden="true" />
            <span>ARCHIVE</span>
          </button>
          <span><Database aria-hidden="true" /> DATABASE</span>
          <a href="#combat"><Swords aria-hidden="true" /> COMBAT</a>
          <span><FolderArchive aria-hidden="true" /> DOSSIER</span>
        </nav>
      </aside>

      <KimiCharacterStage model={model} mode="desktop" />

      <aside
        className="kimi-desktop-character-dossier__right native-scrollbar-hidden"
        data-scroll-owner="dossier-information"
        tabIndex={0}
      >
        <CharacterSummary viewModel={character} />
        <CharacterProgression id="inheritance" title="传承" progression={character.inheritance} />
        <CharacterProgression id="portray" title="塑造" progression={character.portray} />
        <CharacterVoiceRecords voices={character.voices} />
        <CharacterCollection groups={character.collectionGroups} />
        <CharacterTechnicalFooter viewModel={character} />
      </aside>

    </article>
  )
}
