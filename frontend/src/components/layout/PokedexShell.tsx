import React, { useState } from 'react'
import { Menu, X } from 'lucide-react'
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
    <div className="flex flex-col h-screen bg-bg-dark text-text-light overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-pokedex-red border-b-4 border-pokedex-red-dark shrink-0">
        <div className="flex items-center gap-3">
          {/* Mobile menu button */}
          <button
            className="lg:hidden p-1 rounded text-white hover:bg-pokedex-red-dark transition-colors"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={22} />
          </button>
          <h1 className="font-pixel text-pikachu-yellow text-sm md:text-base tracking-wide">
            {title}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {/* Decorative Pokédex lights */}
          <span className="w-3 h-3 rounded-full bg-blue-400 border border-blue-200 animate-pulse" />
          <span className="w-2 h-2 rounded-full bg-red-300 border border-red-100" />
          <span className="w-2 h-2 rounded-full bg-yellow-300 border border-yellow-100" />
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — hidden on mobile, shown on lg+ */}
        <aside className="hidden lg:flex flex-col w-[380px] xl:w-[420px] border-r border-bg-panel bg-bg-panel overflow-y-auto shrink-0">
          {leftPanel}
        </aside>

        {/* Tablet: 60/40 split */}
        <aside className="hidden md:flex lg:hidden flex-col w-[40%] border-r border-bg-panel bg-bg-panel overflow-y-auto shrink-0">
          {leftPanel}
        </aside>

        {/* Right panel */}
        <main className="flex-1 overflow-y-auto bg-bg-dark">
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
