import React from 'react'
import { ChatPanel } from '../components/chat'

const Chat: React.FC = () => {
  return (
    <div className="flex flex-col h-screen bg-bg-dark">
      <header className="px-4 py-3 bg-pokedex-red border-b-4 border-pokedex-red-dark shrink-0">
        <h1 className="font-pixel text-pikachu-yellow text-sm">Pokédex Arcana · Chat</h1>
      </header>
      <div className="flex-1 overflow-hidden">
        <ChatPanel />
      </div>
    </div>
  )
}

export default Chat
