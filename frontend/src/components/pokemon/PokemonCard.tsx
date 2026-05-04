import React, { useState } from 'react'
import TypeBadge from '../ui/TypeBadge'
import { getTypeColor } from '../../design-system/type-colors'

interface PokemonCardProps {
  id: number
  name: string
  types: string[]
  nationalDex?: number
  onClick?: () => void
  selected?: boolean
  className?: string
}

function getSpriteUrl(id: number): string {
  return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${id}.png`
}

const PokemonCard: React.FC<PokemonCardProps> = ({
  id, name, types, onClick, selected = false, className = '',
}) => {
  const [imgError, setImgError] = useState(false)
  const primaryType = types[0] ?? 'normal'
  const typeColor = getTypeColor(primaryType)

  return (
    <button
      className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-xl transition-all text-left group ${className}`}
      style={{
        background: selected
          ? `linear-gradient(135deg, rgba(${hexToRgb(typeColor)}, 0.25), rgba(30,58,95,0.6))`
          : 'rgba(255,255,255,0.03)',
        border: selected
          ? `1px solid rgba(${hexToRgb(typeColor)}, 0.5)`
          : '1px solid rgba(255,255,255,0.05)',
        boxShadow: selected ? `0 0 15px rgba(${hexToRgb(typeColor)}, 0.2)` : 'none',
      }}
      onMouseEnter={e => {
        if (!selected) {
          e.currentTarget.style.background = `rgba(${hexToRgb(typeColor)}, 0.1)`
          e.currentTarget.style.borderColor = `rgba(${hexToRgb(typeColor)}, 0.3)`
        }
      }}
      onMouseLeave={e => {
        if (!selected) {
          e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)'
        }
      }}
      onClick={onClick}
      aria-label={`${name} #${id}`}
      aria-pressed={selected}
    >
      {/* Sprite */}
      <div
        className="w-11 h-11 shrink-0 flex items-center justify-center rounded-lg"
        style={{ background: `rgba(${hexToRgb(typeColor)}, 0.1)` }}
      >
        {!imgError ? (
          <img
            src={getSpriteUrl(id)}
            alt={name}
            className="w-10 h-10 object-contain pixelated group-hover:scale-110 transition-transform"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <span className="text-xl">❓</span>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-[10px] font-mono" style={{ color: 'rgba(148,163,184,0.5)' }}>
            #{String(id).padStart(4, '0')}
          </span>
        </div>
        <p className="text-white font-body font-semibold capitalize truncate text-sm leading-tight">
          {name}
        </p>
        <div className="flex gap-1 mt-1 flex-wrap">
          {types.map(t => (
            <TypeBadge key={t} type={t} size="sm" />
          ))}
        </div>
      </div>
    </button>
  )
}

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `${r},${g},${b}`
}

export default PokemonCard
