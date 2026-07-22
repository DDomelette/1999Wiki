import { useState } from 'react'
import BackgroundFX from '../components/BackgroundFX'
import Header from '../components/Header'
import CharacterStage from '../components/CharacterStage'
import LeftColumn from '../components/LeftColumn'
import RightColumn from '../components/RightColumn'
import BottomControls from '../components/BottomControls'
import { usePageMedia } from '../media/usePageMedia'

export default function AdvancedProfilePage() {
  const [skin, setSkin] = useState('initial')
  // GET /api/wiki/pages/wiki/profile-advanced → mediaLinks[]（契约检查器按 M 可见）
  const mediaLinks = usePageMedia('advanced', 'wiki/profile-advanced')

  return (
    <div className="bg-texture-paper text-on-background overflow-hidden h-screen w-screen flex flex-col font-body-md selection:bg-primary selection:text-surface">
      <BackgroundFX />
      <Header />
      <main className="relative flex-1 w-full h-full overflow-hidden pt-16 z-10">
        <CharacterStage skin={skin} mediaLinks={mediaLinks} />
        <LeftColumn mediaLinks={mediaLinks} />
        <RightColumn />
        <BottomControls skin={skin} onSkinChange={setSkin} mediaLinks={mediaLinks} />
      </main>
    </div>
  )
}
