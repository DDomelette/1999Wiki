import { Archive, Database, FolderArchive, Swords } from 'lucide-react'
import type { CharacterDetailViewModel } from '../characterDetailViewModel'
import { CharacterCollection } from './CharacterCollection'
import { CharacterCulture } from './CharacterCulture'
import {
  CharacterIdentityCard,
  CharacterProfileData,
  CharacterProgression,
  CharacterSummary,
  CharacterTechnicalFooter,
} from './CharacterDossierBlocks'
import { CharacterPortraitStage } from './CharacterPortraitStage'
import { CharacterSkillCards } from './CharacterSkillCards'
import { CharacterVoiceRecords } from './CharacterVoiceRecords'

export function DesktopCharacterDossier({
  viewModel,
  onBack,
}: {
  viewModel: CharacterDetailViewModel
  onBack(): void
}) {
  return (
    <article className="desktop-character-dossier" data-testid="desktop-character-dossier">
      <span className="desktop-character-dossier__watermark desktop-character-dossier__watermark--name" aria-hidden="true">
        {viewModel.identity.exonym || viewModel.identity.name}
      </span>
      <span className="desktop-character-dossier__watermark desktop-character-dossier__watermark--status" aria-hidden="true">
        CONFIDENTIAL
      </span>

      <aside
        className="profile-skill-rail native-scrollbar-hidden"
        data-testid="profile-skill-rail"
        data-scroll-owner="profile-skill-rail"
        tabIndex={0}
      >
        <CharacterIdentityCard viewModel={viewModel} />
        <CharacterSummary viewModel={viewModel} />
        <CharacterProfileData viewModel={viewModel} />
        <div id="combat" className="profile-skill-rail__skills">
          <CharacterSkillCards skills={viewModel.skills} />
        </div>
        <CharacterCulture entries={viewModel.cultureEntries} />
        <CharacterCollection groups={viewModel.collectionGroups} />
        <CharacterTechnicalFooter viewModel={viewModel} />
      </aside>

      <CharacterPortraitStage viewModel={viewModel} mode="desktop" />

      <aside className="inheritance-voice-rail" data-testid="inheritance-voice-rail">
        <CharacterProgression id="inheritance" title="传承" progression={viewModel.inheritance} />
        <CharacterProgression id="portray" title="塑造" progression={viewModel.portray} />
        <CharacterVoiceRecords voices={viewModel.voices} />
      </aside>

      <nav className="desktop-character-dossier__utility" aria-label="详情页快捷操作">
        <button type="button" onClick={onBack} aria-label="返回角色索引">
          <Archive aria-hidden="true" />
          <span>ARCHIVE</span>
        </button>
        <span><Database aria-hidden="true" /> DATABASE</span>
        <a href="#combat"><Swords aria-hidden="true" /> COMBAT</a>
        <span><FolderArchive aria-hidden="true" /> DOSSIER</span>
      </nav>
    </article>
  )
}
