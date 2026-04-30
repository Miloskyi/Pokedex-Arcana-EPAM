import React from 'react'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

interface BaseStats {
  hp: number
  attack: number
  defense: number
  sp_atk: number
  sp_def: number
  speed: number
}

interface StatsRadarChartProps {
  stats: BaseStats
  pokemonName?: string
  color?: string
}

const STAT_LABELS: Record<keyof BaseStats, string> = {
  hp: 'HP',
  attack: 'Attack',
  defense: 'Defense',
  sp_atk: 'Sp. Atk',
  sp_def: 'Sp. Def',
  speed: 'Speed',
}

const POKEDEX_RED = '#CC0000'

const StatsRadarChart: React.FC<StatsRadarChartProps> = ({
  stats,
  pokemonName,
  color = POKEDEX_RED,
}) => {
  const data = (Object.keys(STAT_LABELS) as Array<keyof BaseStats>).map((key) => ({
    stat: STAT_LABELS[key],
    value: stats[key],
    fullMark: 255,
  }))

  return (
    <div className="w-full">
      {pokemonName && (
        <p className="text-center text-xs text-gray-400 font-body mb-2 capitalize">{pokemonName} Base Stats</p>
      )}
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
          <PolarGrid stroke="#444" />
          <PolarAngleAxis
            dataKey="stat"
            tick={{ fill: '#F0F0F0', fontSize: 11, fontFamily: 'Nunito, sans-serif' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 255]}
            tick={{ fill: '#888', fontSize: 9 }}
            tickCount={4}
          />
          <Radar
            name={pokemonName ?? 'Stats'}
            dataKey="value"
            stroke={color}
            fill={color}
            fillOpacity={0.3}
            strokeWidth={2}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#2D2D2D', border: '1px solid #444', borderRadius: 8 }}
            labelStyle={{ color: '#F0F0F0', fontFamily: 'Nunito, sans-serif' }}
            itemStyle={{ color: color }}
            formatter={(value: number) => [value, 'Value']}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default StatsRadarChart
