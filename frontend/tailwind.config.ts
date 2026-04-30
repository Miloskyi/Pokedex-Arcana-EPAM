import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Pokédex UI colors
        'pokedex-red': '#CC0000',
        'pokedex-red-dark': '#990000',
        'screen-blue': '#1E3A5F',
        'pikachu-yellow': '#FFCB05',
        'bg-dark': '#1A1A1A',
        'bg-panel': '#2D2D2D',
        'text-light': '#F0F0F0',
        // Pokémon type colors
        type: {
          normal: '#A8A878',
          fire: '#F08030',
          water: '#6890F0',
          electric: '#F8D030',
          grass: '#78C850',
          ice: '#98D8D8',
          fighting: '#C03028',
          poison: '#A040A0',
          ground: '#E0C068',
          flying: '#A890F0',
          psychic: '#F85888',
          bug: '#A8B820',
          rock: '#B8A038',
          ghost: '#705898',
          dragon: '#7038F8',
          dark: '#705848',
          steel: '#B8B8D0',
          fairy: '#EE99AC',
        },
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'monospace'],
        body: ['Nunito', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
