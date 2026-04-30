// Official Pokémon type colors for all 18 types

export type PokemonType =
  | 'normal'
  | 'fire'
  | 'water'
  | 'electric'
  | 'grass'
  | 'ice'
  | 'fighting'
  | 'poison'
  | 'ground'
  | 'flying'
  | 'psychic'
  | 'bug'
  | 'rock'
  | 'ghost'
  | 'dragon'
  | 'dark'
  | 'steel'
  | 'fairy'

export const TYPE_COLORS: Record<string, string> = {
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
} as const

export const VALID_TYPE_NAMES: string[] = Object.keys(TYPE_COLORS)

export const TYPE_TEXT_COLORS: Record<string, string> = {
  normal: '#FFFFFF',
  fire: '#FFFFFF',
  water: '#FFFFFF',
  electric: '#000000',
  grass: '#FFFFFF',
  ice: '#000000',
  fighting: '#FFFFFF',
  poison: '#FFFFFF',
  ground: '#000000',
  flying: '#FFFFFF',
  psychic: '#FFFFFF',
  bug: '#FFFFFF',
  rock: '#FFFFFF',
  ghost: '#FFFFFF',
  dragon: '#FFFFFF',
  dark: '#FFFFFF',
  steel: '#000000',
  fairy: '#000000',
} as const

// Legacy alias
export const ALL_TYPES: PokemonType[] = VALID_TYPE_NAMES as PokemonType[]

export function isValidType(type: string): type is PokemonType {
  return type in TYPE_COLORS
}

export function getTypeColor(type: string): string {
  if (isValidType(type)) return TYPE_COLORS[type]
  return '#A8A878' // fallback to normal
}

export function getTypeTextColor(type: string): string {
  if (isValidType(type)) return TYPE_TEXT_COLORS[type]
  return '#FFFFFF'
}
