import React, { useState } from 'react'
import TypeBadge from '../ui/TypeBadge'

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
  id,
  name,
  types,
  nationalDex,
  onClick,
  selected = false,
  className = '',
}) => {
  const [imgError, setImgError] = useState(false)
  const spriteUrl = getSpriteUrl(id)

  return (
    <button
      className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg transition-all text-left
        ${selected
          ? 'bg-screen-blue border border-pikachu-yellow'
          : 'bg-bg-panel hover:bg-gray-700 border border-transparent'
        } ${className}`}
      onClick={onClick}
      aria-label={`${name} #${nationalDex}`}
      aria-pressed={selected}
    >
      {/* Sprite */}
      <div className="w-12 h-12 shrink-0 flex items-center justify-center">
        {!imgError ? (
          <img
            src={spriteUrl}
            alt={name}
            className="w-12 h-12 object-contain pixelated"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-xs">
            ?
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-xs font-mono">#{String(nationalDex).padStart(4, '0')}</span>
        </div>
        <p className="text-text-light font-body font-semibold capitalize truncate text-sm">
          {name}
        </p>
        <div className="flex gap-1 mt-0.5 flex-wrap">
          {types.map((t) => (
            <TypeBadge key={t} type={t} size="sm" />
          ))}
        </div>
      </div>
    </button>
  )
}

export default PokemonCard
