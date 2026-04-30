import React from 'react'
import { VALID_TYPE_NAMES } from '../../design-system/type-colors'
import TypeBadge from '../ui/TypeBadge'

interface TypeEffectivenessGridProps {
  typeMatchups: Record<string, number>
}

function multiplierLabel(value: number): string {
  if (value === 0) return '0×'
  if (value === 0.25) return '¼×'
  if (value === 0.5) return '½×'
  if (value === 1) return '1×'
  if (value === 2) return '2×'
  if (value === 4) return '4×'
  return `${value}×`
}

function multiplierStyle(value: number): React.CSSProperties {
  if (value === 0) return { backgroundColor: '#6b7280', color: '#d1d5db' }       // gray
  if (value === 0.25) return { backgroundColor: '#14532d', color: '#86efac' }    // dark green
  if (value === 0.5) return { backgroundColor: '#166534', color: '#4ade80' }     // green
  if (value === 1) return { backgroundColor: '#1f2937', color: '#9ca3af' }       // white/neutral
  if (value === 2) return { backgroundColor: '#7c2d12', color: '#fb923c' }       // orange
  if (value >= 4) return { backgroundColor: '#7f1d1d', color: '#f87171' }        // red
  return { backgroundColor: '#1f2937', color: '#9ca3af' }
}

const TypeEffectivenessGrid: React.FC<TypeEffectivenessGridProps> = ({ typeMatchups }) => {
  return (
    <div className="p-3">
      <h3 className="text-xs font-pixel text-pikachu-yellow mb-3">Type Effectiveness</h3>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5">
        {VALID_TYPE_NAMES.map((type) => {
          const value = typeMatchups[type] ?? 1
          return (
            <div
              key={type}
              className="flex flex-col items-center gap-1 p-1.5 rounded-lg"
              style={{ backgroundColor: '#111827' }}
            >
              <TypeBadge type={type} size="sm" />
              <span
                className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded"
                style={multiplierStyle(value)}
              >
                {multiplierLabel(value)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default TypeEffectivenessGrid
