import React, { useEffect } from 'react'
import { X } from 'lucide-react'

interface MobileDrawerProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
}

const MobileDrawer: React.FC<MobileDrawerProps> = ({ open, onClose, children }) => {
  // Lock body scroll when drawer is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[100] flex md:hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div className="relative flex flex-col w-[85vw] max-w-sm h-full bg-bg-panel shadow-xl overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 bg-pokedex-red border-b border-pokedex-red-dark">
          <span className="font-pixel text-pikachu-yellow text-xs">Menu</span>
          <button
            onClick={onClose}
            className="p-1 rounded text-white hover:bg-pokedex-red-dark transition-colors"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  )
}

export default MobileDrawer
