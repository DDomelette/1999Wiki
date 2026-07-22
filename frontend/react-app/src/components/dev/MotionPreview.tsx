import { useState } from 'react'
import { AnimatedContent } from '../animations/reactbits/AnimatedContent'
import { AnimatedList } from '../animations/reactbits/AnimatedList'
import { ScrollReveal } from '../animations/reactbits/ScrollReveal'
import { TiltedImageCard } from '../ui/TiltedImageCard'
import { getMotionPolicy } from '../../motion/motionPolicy'
import { readMotionDiagnostics } from '../../motion/motionDiagnostics'
import './MotionPreview.css'

export function MotionPreview() {
  const [revision, setRevision] = useState(0)
  const policy = getMotionPolicy()
  const diagnostics = readMotionDiagnostics()
  return <main className="motion-preview" data-revision={revision}>
    <header><h1>Motion Preview</h1><a href="/">Back</a></header>
    <dl><dt>Policy</dt><dd>{policy.reason}</dd><dt>Blur</dt><dd>{String(policy.blur)}</dd><dt>Texture budget</dt><dd>{policy.textureBudget}</dd></dl>
    <section><h2>Animated Content</h2><AnimatedContent key={revision} direction="horizontal">Horizontal entrance</AnimatedContent></section>
    <section><h2>Animated List</h2><AnimatedList items={['Alpha', 'Beta', 'Gamma']} itemKey={String} renderItem={String} ariaLabel="Preview list" /></section>
    <section><h2>Scroll Reveal</h2><ScrollReveal text="Scoped text reveal keeps semantic content readable." scrollContainer={null} baseRotation={0} enabled /></section>
    <section><h2>Tilt</h2><TiltedImageCard src="/assets/global/reverse1999-global-bg.webp" alt="Motion preview" /></section>
    <section><h2>Diagnostics</h2><output>{diagnostics.length} local events</output></section>
    <button type="button" onClick={() => setRevision((value) => value + 1)}>Replay</button>
  </main>
}
