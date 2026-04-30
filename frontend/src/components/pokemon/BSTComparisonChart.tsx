import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface PokemonStats {
  name: string
  hp: number
  attack: number
  defense: number
  sp_atk: number
  sp_def: number
  speed: number
}

interface BSTComparisonChartProps {
  pokemonList: PokemonStats[]
}

const STAT_COLORS = {
  HP: '#FF6B6B',
  Atk: '#FF9F43',
  Def: '#FECA57',
  'Sp. Atk': '#48DBFB',
  'Sp. Def': '#1DD1A1',
  Speed: '#A29BFE',
}

const BSTComparisonChart: React.FC<BSTComparisonChartProps> = ({ pokemonList }) => {
  if (pokemonList.length === 0) {
    return (
      <div className="p-3 text-gray-500 text-xs text-center">No Pokémon to compare.</div>
    )
  }

  // Build data: one entry per pokemon, with all 6 stats
  const data = pokemonList.map((p) => ({
    name: p.name.charAt(0).toUpperCase() + p.name.slice(1),
    HP: p.hp,
    Atk: p.attack,
    Def: p.defense,
    'Sp. Atk': p.sp_atk,
    'Sp. Def': p.sp_def,
    Speed: p.speed,
  }))

  return (
    <div className="w-full">
      <h3 className="text-xs font-pixel text-pikachu-yellow mb-3 px-3">BST Comparison</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis
            dataKey="name"
            tick={{ fill: '#F0F0F0', fontSize: 11, fontFamily: 'Nunito, sans-serif' }}
          />
          <YAxis
            domain={[0, 255]}
            tick={{ fill: '#888', fontSize: 10 }}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#2D2D2D', border: '1px solid #444', borderRadius: 8 }}
            labelStyle={{ color: '#F0F0F0', fontFamily: 'Nunito, sans-serif' }}
            itemStyle={{ fontFamily: 'Nunito, sans-serif' }}
          />
          <Legend
            wrapperStyle={{ color: '#F0F0F0', fontSize: 11, fontFamily: 'Nunito, sans-serif' }}
          />
          {(Object.keys(STAT_COLORS) as Array<keyof typeof STAT_COLORS>).map((stat) => (
            <Bar key={stat} dataKey={stat} fill={STAT_COLORS[stat]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default BSTComparisonChart
