import React, { useState, useEffect, useCallback } from 'react'
import { PokedexShell } from '../components/layout'
import { PokemonCard } from '../components/pokemon'
import { ChatPanel } from '../components/chat'
import { Search, Loader2, Zap } from 'lucide-react'

interface PokemonListItem {
  id: number
  name: string
  types: string[]
}

const POKEAPI = 'https://pokeapi.co/api/v2'

async function fetchPokemonPage(offset: number, limit = 40): Promise<PokemonListItem[]> {
  const res = await fetch(`${POKEAPI}/pokemon?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('PokéAPI error')
  const data = await res.json()
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
    const res = await fetch(`${POKEAPI}/pokemon/${q}`)
    if (res.ok) {
      const d = await res.json()
      const types: string[] = d.types.map((t: { type: { name: string } }) => t.type.name)
      return [{ id: d.id, name: d.name, types }]
    }
  } catch { /* fall through */ }
  try {
    const res = await fetch(`${POKEAPI}/pokemon?limit=300&offset=0`)
    const data = await res.json()
    const matches = data.results.filter((p: { name: string }) => p.name.includes(q)).slice(0, 20)
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

// Quick-access suggestions
const QUICK_QUERIES = [
  { label: '⚡ Pikachu stats', query: 'What are Pikachu\'s base stats?' },
  { label: '🔥 Best fire type', query: 'best fire pokemon' },
  { label: '💧 Blastoise vs Charizard', query: 'Blastoise vs Charizard' },
  { label: '🏆 Dragapult team OU', query: 'I need 5 teammates for Dragapult in OU' },
  { label: '🧬 Mewtwo lore', query: 'Tell me about Mewtwo: its origin and powers' },
  { label: '⚔️ Damage calc', query: 'Bold natured Abomasnow uses Blizzard against Jigglypuff with 0 SpD EVs' },
]

const Home: React.FC = () => {
  const [pokemonList, setPokemonList] = useState<PokemonListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [chatInput, setChatInput] = useState('')

  useEffect(() => {
    setLoading(true)
    fetchPokemonPage(0, 40).then(setPokemonList).catch(console.error).finally(() => setLoading(false))
  }, [])

  const handleSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      setLoading(true)
      fetchPokemonPage(0, 40).then(setPokemonList).catch(console.error).finally(() => setLoading(false))
      return
    }
    setSearching(true)
    try {
      const results = await searchPokemon(query)
      setPokemonList(results)
    } catch (e) { console.error(e) }
    finally { setSearching(false) }
  }, [])

  useEffect(() => {
    if (!searchQuery) {
      setLoading(true)
      fetchPokemonPage(0, 40).then(setPokemonList).catch(console.error).finally(() => setLoading(false))
      return
    }
    const timer = setTimeout(() => handleSearch(searchQuery), 400)
    return () => clearTimeout(timer)
  }, [searchQuery, handleSearch])

  const leftPanel = (
    <div className="flex flex-col h-full">

      {/* Panel header */}
      <div
        className="px-4 py-3 shrink-0"
        style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2040 100%)',
          borderBottom: '2px solid #2d4a7a',
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Zap size={14} className="text-pikachu-yellow" />
          <span className="font-pixel text-pikachu-yellow" style={{ fontSize: '9px' }}>
            POKÉDEX DATABASE
          </span>
        </div>

        {/* Search */}
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleSearch(searchQuery) } }}
            placeholder="Search Pokémon..."
            className="w-full pl-8 pr-8 py-2 text-sm font-body text-white placeholder-blue-400/60 rounded-lg focus:outline-none transition-all"
            style={{
              background: 'rgba(0,0,0,0.4)',
              border: '1px solid rgba(59,130,246,0.3)',
              fontSize: '13px',
            }}
            onFocus={e => { e.target.style.borderColor = 'rgba(255,203,5,0.6)'; e.target.style.boxShadow = '0 0 12px rgba(255,203,5,0.2)' }}
            onBlur={e => { e.target.style.borderColor = 'rgba(59,130,246,0.3)'; e.target.style.boxShadow = 'none' }}
          />
          {(loading || searching) && (
            <Loader2 size={13} className="absolute right-3 top-1/2 -translate-y-1/2 text-pikachu-yellow animate-spin" />
          )}
        </div>
      </div>

      {/* Pokémon list */}
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        {loading && pokemonList.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <div className="relative w-12 h-12">
              <div className="w-12 h-12 rounded-full border-2 border-pikachu-yellow/30 animate-spin border-t-pikachu-yellow" />
            </div>
            <p className="text-blue-400 text-xs font-body">Loading Pokédex...</p>
          </div>
        )}

        {!loading && pokemonList.length === 0 && searchQuery && (
          <div className="text-center py-8">
            <p className="text-4xl mb-2">🔍</p>
            <p className="text-gray-400 text-xs font-body">No Pokémon found for "{searchQuery}"</p>
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

      {/* Quick queries footer */}
      <div
        className="shrink-0 px-3 py-3 border-t"
        style={{ borderTopColor: '#2d4a7a', background: 'rgba(0,0,0,0.3)' }}
      >
        <p className="font-pixel text-blue-400 mb-2" style={{ fontSize: '8px' }}>QUICK QUERIES</p>
        <div className="flex flex-wrap gap-1">
          {QUICK_QUERIES.map((q, i) => (
            <button
              key={i}
              onClick={() => {
                // Dispatch to chat via custom event
                window.dispatchEvent(new CustomEvent('pokedex:quick-query', { detail: q.query }))
              }}
              className="text-[10px] font-body px-2 py-1 rounded-full transition-all hover:scale-105"
              style={{
                background: 'rgba(30,58,95,0.8)',
                border: '1px solid rgba(59,130,246,0.3)',
                color: '#93c5fd',
              }}
              onMouseEnter={e => {
                (e.target as HTMLElement).style.borderColor = 'rgba(255,203,5,0.5)'
                ;(e.target as HTMLElement).style.color = '#fbbf24'
              }}
              onMouseLeave={e => {
                (e.target as HTMLElement).style.borderColor = 'rgba(59,130,246,0.3)'
                ;(e.target as HTMLElement).style.color = '#93c5fd'
              }}
            >
              {q.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <PokedexShell
      leftPanel={leftPanel}
      rightPanel={<ChatPanel externalInput={chatInput} onExternalInputConsumed={() => setChatInput('')} />}
    />
  )
}

export default Home
