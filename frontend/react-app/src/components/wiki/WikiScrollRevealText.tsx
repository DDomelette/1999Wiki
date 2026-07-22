import { ScrollReveal } from '../animations/reactbits/ScrollReveal'
import { getWikiMotionProfile } from './wikiMotionProfiles'

export function WikiScrollRevealText({ text, enabled, as = 'p', pageType = '' }: { text: string; enabled: boolean; as?: 'p' | 'h1' | 'h2' | 'h3'; pageType?: string }) {
  const profile = getWikiMotionProfile(pageType)
  return <ScrollReveal text={text} scrollContainer={null} baseRotation={0} enabled={enabled} as={as} blurStrength={profile.revealBlur} revealStart={profile.revealStart} />
}
