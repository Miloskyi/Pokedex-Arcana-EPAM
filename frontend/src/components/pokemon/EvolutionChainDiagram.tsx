import React, { useState } from 'react'
import { ChevronRight } from 'lucide-react'

interface EvolutionStage {
  name: string
  stage: number
  trigger?: string
  condition_detail?: Record<string, unknown>
}

interface EvolutionChainDiagramProps {
  chain: EvolutionStage[]
  onSelectPokemon?: (name: string) => void
}

function formatCondition(stage: EvolutionStage): string {
  if (!stage.trigger) return ''
  const detail = stage.condition_detail ?? {}
  const parts: string[] = [stage.trigger.replace(/-/g, ' ')]
  if ('min_level' in detail) parts.push(`Lv. ${detail.min_level}`)
  if ('item' in detail) parts.push(String(detail.item).replace(/-/g, ' '))
  if ('min_happiness' in detail) parts.push(`Happiness ${detail.min_happiness}`)
  if ('time_of_day' in detail) parts.push(String(detail.time_of_day))
  return parts.join(' · ')
}

// Derive a numeric ID from the name for sprite lookup (fallback: 0)
function getSpriteUrl(name: string): string {
  return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${name}.png`
}

const EvolutionChainDiagram: React.FC<EvolutionChainDiagramProps> = ({ chain, onSelectPokemon }) => {
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({})

  if (chain.length === 0) {
    return (
      <div className="p-3 text-gray-500 text-xs text-center">No evolution data available.</div>
    )
  }

  // Sort by stage to ensure correct order
  const sorted = [...chain].sort((a, b) => a.stage - b.stage)

  return (
    <div className="p-3">
      <h3 className="text-xs font-pixel text-pikachu-yellow mb-3">Evolution Chain</h3>
      <div className="flex items-center gap-1 flex-wrap">
        {sorted.map((stage, idx) => (
          <React.Fragment key={`${stage.name}-${stage.stage}`}>
            {/* Stage node */}
            <button
              className="flex flex-col items-center gap-1 p-2 rounded-lg hover:bg-bg-panel transition-colors group"
              onClick={() => onSelectPokemon?.(stage.name)}
              aria-label={`Select ${stage.name}`}
            >
              <div className="w-14 h-14 flex items-center justify-center">
                {!imgErrors[stage.name] ? (
                  <img
                    src={getSpriteUrl(stage.name)}
                    alt={stage.name}
                    className="w-14 h-14 object-contain pixelated group-hover:scale-110 transition-transform"
                    onError={() => setImgErrors((prev) => ({ ...prev, [stage.name]: true }))}
                    loading="lazy"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-xs">
                    ?
                  </div>
                )}
              </div>
              <span className="text-text-light text-xs capitalize font-body font-semibold">
                {stage.name}
              </span>
              <span className="text-gray-500 text-[9px] font-mono">
                Stage {stage.stage}
              </span>
            </button>

            {/* Arrow + condition (between stages) */}
            {idx < sorted.length - 1 && (
              <div className="flex flex-col items-center gap-0.5 px-1">
                <ChevronRight size={16} className="text-pikachu-yellow" />
                {sorted[idx + 1].trigger && (
                  <span className="text-[8px] text-gray-400 text-center max-w-[60px] leading-tight">
                    {formatCondition(sorted[idx + 1])}
                  </span>
                )}
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

export default EvolutionChainDiagram
