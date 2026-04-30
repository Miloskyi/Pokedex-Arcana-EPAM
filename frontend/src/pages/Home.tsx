import React, { useState, useEffect, useCallback } from 'react'
import { PokedexShell } from '../components/layout'
import { PokemonCard } from '../components/pokemon'
import { ChatPanel } from '../components/chat'
import { Search, Loader2 } from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface PokemonListItem {
  id: number
  name: string
  types: string[]
}

// ─── PokéAPI helpers ─────────────────────────────────────────────────────────

const POKEAPI = 'https://pokeapi.co/api/v2'

async function fetchPokemonPage(offset: number, limit = 40): Promise<PokemonListItem[]> {
  const res = await fetch(`${POKEAPI}/pokemon?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('PokéAPI error')
  const data = await res.json()

  // Fetch types for each Pokémon in parallel (batched)
  const items: PokemonListItem[] = await Promise.all(
    data.results.map(async (p: { name: string; url: string }) => {
      const id = parseInt(p.url.split('/').filter(Boolean).pop() ?? '0', 10)
      try {
        const detail = await fetch(`${POKEAPI}/pokemon/${id}`)
        const d = await detail.json()
        const types: string[] = d.types.map((t: { type: { name: string } }) => t.type.name)
        return { id, name: p.name, types }
      } catch {
        return { id, name: p.name, types: [] }
      }
    })
  )
  return items
}

async function searchPokemon(query: string): Promise<PokemonListItem[]> {
  const q = query.toLowerCase().trim()
  if (!q) return []
  try {
    // Try exact match first
    const res = await fetch(`${POKEAPI}/pokemon/${q}`)
    if (res.ok) {
      const d = await res.json()
      const types: string[] = d.types.map((t: { type: { name: string } }) => t.type.name)
      return [{ id: d.id, name: d.name, types }]
    }
  } catch { /* fall through to list search */ }

  // Fallback: search through the full list (first 300)
  try {
    const res = await fetch(`${POKEAPI}/pokemon?limit=300&offset=0`)
    const data = await res.json()
    const matches = data.results.filter((p: { name: string }) =>
      p.name.includes(q)
    ).slice(0, 20)

    return Promise.all(
      matches.map(async (p: { name: string; url: string }) => {
        const id = parseInt(p.url.split('/').filter(Boolean).pop() ?? '0', 10)
        try {
          const detail = await fetch(`${POKEAPI}/pokemon/${id}`)
          const d = await detail.json()
          const types: string[] = d.types.map((t: { type: { name: string } }) => t.type.name)
          return { id, name: p.name, types }
        } catch {
          return { id, name: p.name, types: [] }
        }
      })
    )
  } catch {
    return []
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

const Home: React.FC = () => {
  const [pokemonList, setPokemonList] = useState<PokemonListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // Load initial list on mount
  useEffect(() => {
    setLoading(true)
    fetchPokemonPage(0, 40)
      .then(setPokemonList)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Handle search — called on input change (debounced) or Enter
  const handleSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      // Reset to default list
      setLoading(true)
      fetchPokemonPage(0, 40)
        .then(setPokemonList)
        .catch(console.error)
        .finally(() => setLoading(false))
      return
    }
    setSearching(true)
    try {
      const results = await searchPokemon(query)
      setPokemonList(results)
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }, [])

  // Debounce search as user types
  useEffect(() => {
    if (!searchQuery) {
      // Restore default list when cleared
      setLoading(true)
      fetchPokemonPage(0, 40)
        .then(setPokemonList)
        .catch(console.error)
        .finally(() => setLoading(false))
      return
    }
    const timer = setTimeout(() => handleSearch(searchQuery), 400)
    return () => clearTimeout(timer)
  }, [searchQuery, handleSearch])

  const leftPanel = (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="px-3 py-3 border-b border-gray-700">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => {
              // Prevent form submit / page reload on Enter
              if (e.key === 'Enter') {
                e.preventDefault()
                handleSearch(searchQuery)
              }
            }}
            placeholder="Search Pokémon..."
            className="w-full bg-bg-dark border border-gray-600 rounded-lg pl-8 pr-3 py-2 text-text-light text-sm font-body placeholder-gray-500 focus:outline-none focus:border-pikachu-yellow transition-colors"
            aria-label="Search Pokémon"
          />
          {(loading || searching) && (
            <Loader2
              size={14}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-pikachu-yellow animate-spin"
            />
          )}
        </div>
      </div>

      {/* Pokémon list */}
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        {loading && pokemonList.length === 0 && (
          <div className="flex items-center justify-center py-8 text-gray-500 text-xs font-body gap-2">
            <Loader2 size={14} className="animate-spin" />
            Loading Pokémon...
          </div>
        )}

        {!loading && pokemonList.length === 0 && searchQuery && (
          <div className="text-center py-8 text-gray-500 text-xs font-body">
            No Pokémon found for "{searchQuery}"
          </div>
        )}

        {pokemonList.map(p => (
          <PokemonCard
            key={p.id}
            id={p.id}
            name={p.name}
            types={p.types}
            selected={selectedId === p.id}
            onClick={() => setSelectedId(p.id)}
          />
        ))}
      </div>
    </div>
  )

  return (
    <PokedexShell
      leftPanel={leftPanel}
      rightPanel={<ChatPanel />}
    />
  )
}

export default Home
