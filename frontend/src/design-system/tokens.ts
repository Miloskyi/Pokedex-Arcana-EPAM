// Design system tokens for Pokédex Arcana

export const COLORS = {
  pokedexRed: '#CC0000',
  pokedexRedDark: '#990000',
  screenBlue: '#1E3A5F',
  pikachuYellow: '#FFCB05',
  bgDark: '#1A1A1A',
  bgPanel: '#2D2D2D',
  textLight: '#F0F0F0',
  white: '#FFFFFF',
  black: '#000000',
} as const

export const FONTS = {
  pixel: '"Press Start 2P", monospace',
  body: 'Nunito, Inter, sans-serif',
  mono: '"JetBrains Mono", monospace',
} as const

export const BREAKPOINTS = {
  mobile: '640px',
  tablet: '768px',
  desktop: '1024px',
} as const

// Legacy aliases for backward compatibility
export const colors = COLORS
export const fonts = FONTS
export const breakpoints = BREAKPOINTS

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  '2xl': '48px',
  '3xl': '64px',
} as const

export const borderRadius = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '9999px',
} as const

export const shadows = {
  sm: '0 1px 2px rgba(0,0,0,0.3)',
  md: '0 4px 6px rgba(0,0,0,0.4)',
  lg: '0 10px 15px rgba(0,0,0,0.5)',
} as const

export const zIndex = {
  drawer: 100,
  modal: 200,
  tooltip: 300,
  toast: 400,
} as const
