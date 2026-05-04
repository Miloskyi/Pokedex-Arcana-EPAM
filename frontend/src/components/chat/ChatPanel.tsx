import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Send, RefreshCw, Wifi, WifiOff, Zap } from 'lucide-react'
import { useWebSocket, ServerEvent } from '../../hooks/useWebSocket'
import { useStreamBuffer } from '../../hooks/useStreamBuffer'
import { useSessionStore, generateId } from '../../store/sessionStore'
import MessageBubble from './MessageBubble'
import AgentActivityBar from './AgentActivityBar'

interface ChatPanelProps {
  externalInput?: string
  onExternalInputConsumed?: () => void
}

const ChatPanel: React.FC<ChatPanelProps> = ({ externalInput, onExternalInputConsumed }) => {
  const {
    sessionId, messages, activeAgents, isStreaming,
    addMessage, appendToLastMessage, finalizeLastMessage,
    setAgentActivity, clearAgentActivity, setStreaming,
  } = useSessionStore()

  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { push: pushToken, flush: flushTokens, reset: resetBuffer } = useStreamBuffer({ flushIntervalMs: 30 })

  // Handle quick queries from left panel
  useEffect(() => {
    const handler = (e: Event) => {
      const query = (e as CustomEvent).detail as string
      setInputValue(query)
      inputRef.current?.focus()
    }
    window.addEventListener('pokedex:quick-query', handler)
    return () => window.removeEventListener('pokedex:quick-query', handler)
  }, [])

  // Handle external input (from parent)
  useEffect(() => {
    if (externalInput) {
      setInputValue(externalInput)
      onExternalInputConsumed?.()
      inputRef.current?.focus()
    }
  }, [externalInput, onExternalInputConsumed])

  const handleEvent = useCallback((event: ServerEvent) => {
    try {
      switch (event.event) {
        case 'token': {
          const token = typeof event.data === 'string' ? event.data : String(event.data ?? '')
          pushToken(token)
          appendToLastMessage(token)
          break
        }
        case 'agent_activity': {
          let agentName = 'Agent'
          if (typeof event.data === 'string') agentName = event.data
          else if (event.data && typeof event.data === 'object')
            agentName = (event.data as { agent_name?: string }).agent_name ?? 'Agent'
          setAgentActivity({ agentName, status: 'active', startedAt: Date.now() })
          break
        }
        case 'done': {
          flushTokens(); finalizeLastMessage(); setStreaming(false); clearAgentActivity()
          break
        }
        case 'error': {
          const errMsg = typeof event.data === 'string' ? event.data : 'An error occurred'
          appendToLastMessage(errMsg.startsWith('⚠️') ? errMsg : `⚠️ ${errMsg}`)
          flushTokens(); finalizeLastMessage(); setStreaming(false); clearAgentActivity()
          break
        }
      }
    } catch (err) { console.error('ChatPanel handleEvent error:', err) }
  }, [pushToken, flushTokens, appendToLastMessage, finalizeLastMessage, setAgentActivity, clearAgentActivity, setStreaming])

  const { readyState, send, reconnect } = useWebSocket({ sessionId, onEvent: handleEvent, enabled: true })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(() => {
    const query = inputValue.trim()
    if (!query || isStreaming || readyState !== 'open') return
    addMessage({ id: generateId(), role: 'user', content: query, timestamp: Date.now() })
    addMessage({ id: generateId(), role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true })
    resetBuffer(); setStreaming(true)
    send({ query, session_id: sessionId })
    setInputValue('')
  }, [inputValue, isStreaming, readyState, addMessage, resetBuffer, setStreaming, send, sessionId])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const isConnected = readyState === 'open'

  return (
    <div className="flex flex-col h-full" style={{ background: 'transparent' }}>

      {/* Connection bar */}
      <div
        className="shrink-0 flex items-center gap-2 px-4 py-1.5 text-xs"
        style={{
          background: isConnected ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
          borderBottom: `1px solid ${isConnected ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
        }}
      >
        {isConnected
          ? <Wifi size={11} className="text-green-400" />
          : <WifiOff size={11} className="text-red-400" />}
        <span className={isConnected ? 'text-green-400' : 'text-red-400'}>
          {isConnected ? '● Connected to Pokédex AI' : readyState === 'connecting' ? '◌ Connecting...' : '○ Disconnected'}
        </span>
        {!isConnected && (
          <button onClick={reconnect} className="ml-auto flex items-center gap-1 text-red-300 hover:text-red-100 transition-colors">
            <RefreshCw size={10} />
            <span>Retry</span>
          </button>
        )}
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-5 py-8">
            {/* Animated Pokéball */}
            <div className="relative w-20 h-20 animate-bounce" style={{ animationDuration: '3s' }}>
              <div
                className="w-20 h-20 rounded-full border-4 border-white/20 overflow-hidden"
                style={{ boxShadow: '0 0 30px rgba(204,0,0,0.4), 0 0 60px rgba(204,0,0,0.1)' }}
              >
                <div className="w-full h-1/2" style={{ background: 'linear-gradient(135deg, #CC0000, #ff4444)' }} />
                <div className="w-full h-1/2" style={{ background: 'linear-gradient(135deg, #1a1a1a, #333)' }} />
                <div
                  className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-white border-4 border-gray-600"
                  style={{ boxShadow: '0 0 10px rgba(255,255,255,0.5)' }}
                />
                <div className="absolute top-1/2 left-0 right-0 h-1 bg-gray-800 -translate-y-1/2" />
              </div>
            </div>

            <div>
              <h2
                className="font-pixel text-pikachu-yellow mb-2"
                style={{ fontSize: '12px', textShadow: '0 0 20px rgba(255,203,5,0.5)' }}
              >
                POKÉDEX ARCANA
              </h2>
              <p className="text-blue-300 text-sm font-body mb-4 max-w-sm">
                Your AI-powered Pokémon expert. Ask me anything!
              </p>
            </div>

            {/* Example queries */}
            <div className="grid grid-cols-1 gap-2 w-full max-w-md">
              {[
                { icon: '📊', text: 'What are Jigglypuff\'s base stats?' },
                { icon: '⚔️', text: 'Bold Abomasnow uses Blizzard vs Jigglypuff 0 SpD EVs' },
                { icon: '🏆', text: 'I need 5 teammates for Dragapult in OU' },
                { icon: '📖', text: 'Tell me about Mewtwo\'s origin' },
              ].map((ex, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setInputValue(ex.text)
                    inputRef.current?.focus()
                  }}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-left text-sm font-body transition-all hover:scale-[1.02]"
                  style={{
                    background: 'rgba(30,58,95,0.4)',
                    border: '1px solid rgba(59,130,246,0.2)',
                    color: '#93c5fd',
                  }}
                  onMouseEnter={e => {
                    const el = e.currentTarget
                    el.style.background = 'rgba(30,58,95,0.7)'
                    el.style.borderColor = 'rgba(255,203,5,0.4)'
                    el.style.color = '#fbbf24'
                  }}
                  onMouseLeave={e => {
                    const el = e.currentTarget
                    el.style.background = 'rgba(30,58,95,0.4)'
                    el.style.borderColor = 'rgba(59,130,246,0.2)'
                    el.style.color = '#93c5fd'
                  }}
                >
                  <span className="text-lg">{ex.icon}</span>
                  <span>{ex.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            citations={msg.citations}
            verified={msg.verification?.verified}
            discrepancyDetected={msg.verification?.discrepancyDetected}
            agentValue={msg.verification?.agentValue}
            referenceValue={msg.verification?.referenceValue}
            isStreaming={msg.isStreaming}
            agentName={msg.agentName}
            timestamp={msg.timestamp}
            id={msg.id}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Agent activity */}
      <AgentActivityBar agents={activeAgents} />

      {/* Input area */}
      <div
        className="shrink-0 px-4 py-3"
        style={{
          background: 'linear-gradient(0deg, rgba(15,15,26,0.98) 0%, rgba(15,15,26,0.9) 100%)',
          borderTop: '1px solid rgba(59,130,246,0.15)',
        }}
      >
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isConnected ? '✦ Ask about any Pokémon...' : 'Waiting for connection...'}
              rows={1}
              disabled={isStreaming || !isConnected}
              className="w-full resize-none text-sm font-body text-white placeholder-blue-400/50 rounded-xl px-4 py-3 focus:outline-none transition-all disabled:opacity-40 max-h-32 overflow-y-auto"
              style={{
                minHeight: '46px',
                background: 'rgba(30,58,95,0.3)',
                border: '1px solid rgba(59,130,246,0.25)',
              }}
              onFocus={e => {
                e.target.style.borderColor = 'rgba(255,203,5,0.5)'
                e.target.style.boxShadow = '0 0 20px rgba(255,203,5,0.1)'
                e.target.style.background = 'rgba(30,58,95,0.5)'
              }}
              onBlur={e => {
                e.target.style.borderColor = 'rgba(59,130,246,0.25)'
                e.target.style.boxShadow = 'none'
                e.target.style.background = 'rgba(30,58,95,0.3)'
              }}
              aria-label="Chat input"
            />
          </div>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming || !isConnected}
            className="shrink-0 w-12 h-12 rounded-xl flex items-center justify-center transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
            style={{
              background: inputValue.trim() && isConnected && !isStreaming
                ? 'linear-gradient(135deg, #CC0000, #ff4444)'
                : 'rgba(100,100,100,0.3)',
              boxShadow: inputValue.trim() && isConnected && !isStreaming
                ? '0 0 20px rgba(204,0,0,0.4)'
                : 'none',
            }}
            aria-label="Send message"
          >
            {isStreaming
              ? <Zap size={16} className="text-pikachu-yellow animate-pulse" />
              : <Send size={16} className="text-white" />}
          </button>
        </div>

        <div className="flex items-center justify-between mt-1.5">
          <p className="text-[10px] font-body" style={{ color: 'rgba(147,197,253,0.4)' }}>
            Powered by llama3.1:8b · PokéAPI · Bulbapedia RAG
          </p>
          <p className="text-[10px] font-body" style={{ color: 'rgba(147,197,253,0.3)' }}>
            Enter ↵ send · Shift+Enter newline
          </p>
        </div>
      </div>
    </div>
  )
}

export default ChatPanel
