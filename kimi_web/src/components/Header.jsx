import { useEffect, useState } from 'react'

function useSysTime() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return now.toTimeString().slice(0, 8)
}

export default function Header() {
  const sysTime = useSysTime()

  return (
    <header className="fixed top-0 left-0 w-full z-40 flex justify-between items-center px-8 py-3 border-b border-outline/20 bg-surface/40 backdrop-blur-md shadow-hard">
      <div className="flex items-center gap-8">
        <div className="flex flex-col">
          <span className="font-headline-md text-primary tracking-widest uppercase text-xl leading-none">REVERSE:1999</span>
          <span className="font-data-mono text-[9px] text-outline tracking-widest mt-1">FOUNDATION_ARCHIVE_ACCESS // TERMINAL_03</span>
        </div>
        <div className="h-8 w-[1px] bg-outline/30 mx-4"></div>
        <nav className="flex gap-6 font-data-mono text-xs">
          <a className="text-primary hover:text-primary-container transition-colors relative group" href="#">
            [ ARCHIVE ]
            <span className="absolute -bottom-1 left-0 w-full h-[1px] bg-primary scale-x-100 transition-transform"></span>
          </a>
          <a className="text-on-surface/60 hover:text-on-surface transition-colors" href="#">PERSONNEL</a>
          <a className="text-on-surface/60 hover:text-on-surface transition-colors" href="#">CHRONO_MAP</a>
        </nav>
      </div>
      <div className="flex items-center gap-4">
        <div className="font-data-mono text-[10px] text-right text-outline">
          <div>SESSION_ID: <span className="text-on-surface">7F22A1_DRUVIS</span></div>
          <div>SYS_TIME: <span className="text-primary animate-pulse">{sysTime}</span></div>
        </div>
        <div className="w-2 h-2 rounded-full bg-error shadow-glow"></div>
      </div>
    </header>
  )
}
