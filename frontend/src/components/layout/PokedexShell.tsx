import React, { useState } from 'react'
import { Menu } from 'lucide-react'
import MobileDrawer from './MobileDrawer'

interface PokedexShellProps {
  leftPanel: React.ReactNode
  rightPanel: React.ReactNode
  title?: string
}

const PokedexShell: React.FC<PokedexShellProps> = ({
  leftPanel,
  rightPanel,
  title = 'Pokédex Arcana',
}) => {
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: '#0f0f0f' }}>

      {/* ── Header ── */}
      <header
        className="shrink-0 flex items-center justify-between px-4 py-2 border-b-4"
        style={{
          background: 'linear-gradient(135deg, #CC0000 0%, #990000 60%, #7a0000 100%)',
          borderBottomColor: '#660000',
          boxShadow: '0 4px 20px rgba(204,0,0,0.5)',
        }}
      >
        {/* Left: menu + title */}
        <div className="flex items-center gap-3">
          <button
            className="lg:hidden p-1.5 rounded-lg text-white hover:bg-white/10 transition-colors"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={20} />
          </button>

          {/* Pokéball icon */}
          <div className="relative w-8 h-8 shrink-0">
            <div className="w-8 h-8 rounded-full border-2 border-white/40 overflow-hidden">
              <div className="w-full h-1/2 bg-white/90" />
              <div className="w-full h-1/2 bg-gray-900" />
              <div
                className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-gray-400"
                style={{ boxShadow: '0 0 6px rgba(255,255,255,0.8)' }}
              />
              <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-gray-700" />
            </div>
          </div>

          <div>
            <h1
              className="font-pixel text-pikachu-yellow leading-none"
              style={{ fontSize: '11px', textShadow: '0 0 10px rgba(255,203,5,0.6)' }}
            >
              {title}
            </h1>
            <p className="text-red-200 text-[9px] font-body opacity-70 mt-0.5">
              AI-Powered Pokémon Intelligence
            </p>
          </div>
        </div>

        {/* Right: decorative lights */}
        <div className="flex items-center gap-3">
          {/* Big blue light */}
          <div
            className="w-5 h-5 rounded-full border-2 border-blue-200/50 animate-pulse"
            style={{
              background: 'radial-gradient(circle at 35% 35%, #93c5fd, #1d4ed8)',
              boxShadow: '0 0 12px rgba(59,130,246,0.8)',
            }}
          />
          {/* Small lights */}
          <div className="flex gap-1.5">
            {['#ef4444', '#facc15', '#22c55e'].map((color, i) => (
              <div
                key={i}
                className="w-2.5 h-2.5 rounded-full border border-white/20"
                style={{ background: color, boxShadow: `0 0 6px ${color}` }}
              />
            ))}
          </div>
          {/* Screen indicator */}
          <div
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-full text-[9px] font-pixel text-green-300"
            style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(34,197,94,0.3)' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            ONLINE
          </div>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel — desktop */}
        <aside
          className="hidden lg:flex flex-col w-[360px] xl:w-[400px] shrink-0 overflow-y-auto border-r"
          style={{
            background: 'linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)',
            borderRightColor: '#2d2d4e',
          }}
        >
          {leftPanel}
        </aside>

        {/* Left panel — tablet */}
        <aside
          className="hidden md:flex lg:hidden flex-col w-[40%] shrink-0 overflow-y-auto border-r"
          style={{
            background: 'linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)',
            borderRightColor: '#2d2d4e',
          }}
        >
          {leftPanel}
        </aside>

        {/* Right panel — chat */}
        <main
          className="flex-1 overflow-hidden"
          style={{ background: 'linear-gradient(180deg, #0f0f1a 0%, #0a0a14 100%)' }}
        >
          {rightPanel}
        </main>
      </div>

      {/* Mobile drawer */}
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        {leftPanel}
      </MobileDrawer>
    </div>
  )
}

export default PokedexShell
