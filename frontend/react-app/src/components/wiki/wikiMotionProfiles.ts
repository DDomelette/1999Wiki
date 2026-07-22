export interface WikiMotionProfile {
  distance: number
  staggerStep: number
  accent: string
  revealBlur: number
  revealStart: number
}

const PROFILES: Record<string, WikiMotionProfile> = {
  character: { distance: 34, staggerStep: 5, accent: '#a56c36', revealBlur: 5, revealStart: 88 },
  story: { distance: 22, staggerStep: 3, accent: '#7b8d86', revealBlur: 3, revealStart: 92 },
  item: { distance: 26, staggerStep: 4, accent: '#98695d', revealBlur: 4, revealStart: 90 },
  psychube: { distance: 30, staggerStep: 4, accent: '#77709b', revealBlur: 6, revealStart: 86 },
  default: { distance: 24, staggerStep: 4, accent: 'var(--accent-rust)', revealBlur: 5, revealStart: 90 },
}

export function getWikiMotionProfile(pageType = '', animationProfile = ''): WikiMotionProfile {
  return PROFILES[pageType] ?? PROFILES[animationProfile] ?? PROFILES.default
}
