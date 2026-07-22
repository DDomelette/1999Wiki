export interface MotionPolicy {
  enabled: boolean
  blur: boolean
  dpr: number
  textureBudget: number
  reason: 'full' | 'reduced-motion' | 'save-data' | 'low-capability'
}

type NavigatorCapabilities = Navigator & {
  deviceMemory?: number
  connection?: { saveData?: boolean }
}

export function getMotionPolicy(): MotionPolicy {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return { enabled: false, blur: false, dpr: 1, textureBudget: 3, reason: 'low-capability' }
  }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return { enabled: false, blur: false, dpr: 1, textureBudget: 3, reason: 'reduced-motion' }
  }
  const capabilities = navigator as NavigatorCapabilities
  if (capabilities.connection?.saveData) {
    return { enabled: true, blur: false, dpr: 1, textureBudget: 3, reason: 'save-data' }
  }
  const lowCapability = (capabilities.hardwareConcurrency > 0 && capabilities.hardwareConcurrency <= 4)
    || (capabilities.deviceMemory != null && capabilities.deviceMemory <= 4)
  if (lowCapability) {
    return { enabled: true, blur: false, dpr: 1, textureBudget: 5, reason: 'low-capability' }
  }
  return { enabled: true, blur: true, dpr: Math.min(window.devicePixelRatio || 1, 2), textureBudget: 9, reason: 'full' }
}
