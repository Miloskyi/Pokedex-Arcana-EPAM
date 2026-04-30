import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Send, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { useWebSocket, ServerEvent } from '../../hooks/useWebSocket'
import { useStreamBuffer } from '../../hooks/useStreamBuffer'
import { useSessionStore, generateId } from '../../store/sessionStore'
import MessageBubble from './MessageBubble'
import AgentActivityBar from './AgentActivityBar'

const ChatPanel: React.FC = () => {
  const {
    sessionId,
    messages,
    activeAgents,
    isStreaming,
    addMessage,
    appendToLastMessage,
    finalizeLastMessage,
    setAgentActivity,
    clearAgentActivity,
    setStreaming,
  } = useSessionStore()

  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Stream buffer — just accumulates tokens, no onFlush needed
  const { push: pushToken, flush: flushTokens, reset: resetBuffer } = useStreamBuffer({
    flushIntervalMs: 30,
  })

  const handleEvent = useCallback(
    (event: ServerEvent) => {
      try {
        switch (event.event) {
          case 'token': {
            const token = typeof event.data === 'string' ? event.data : String(event.data ?? '')
            pushToken(token)
            appendToLastMessage(token)
            break
          }
          case 'agent_activity': {
            // Backend sends data as a plain string like "Stats Agent"
            // or as an object { agent_name, status }
            let agentName = 'Agent'
            if (typeof event.data === 'string') {
              agentName = event.data
            } else if (event.data && typeof event.data === 'object') {
              agentName = (event.data as { agent_name?: string }).agent_name ?? 'Agent'
            }
            setAgentActivity({
              agentName,
              status: 'active',
              startedAt: Date.now(),
            })
            break
          }
          case 'citation':
            // Citations are informational — no state update needed here
            break
          case 'done': {
            flushTokens()
            finalizeLastMessage()
            setStreaming(false)
            clearAgentActivity()
            break
          }
          case 'error': {
            const errMsg = typeof event.data === 'string' ? event.data : 'An error occurred'
            appendToLastMessage(errMsg.startsWith('⚠️') ? errMsg : `⚠️ ${errMsg}`)
            flushTokens()
            finalizeLastMessage()
            setStreaming(false)
            clearAgentActivity()
            break
          }
          default:
            break
        }
      } catch (err) {
        console.error('ChatPanel handleEvent error:', err)
      }
    },
    [pushToken, flushTokens, appendToLastMessage, finalizeLastMessage, setAgentActivity, clearAgentActivity, setStreaming],
  )

  const { readyState, send, reconnect } = useWebSocket({
    sessionId,
    onEvent: handleEvent,
    enabled: true,
  })

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(() => {
    const query = inputValue.trim()
    if (!query || isStreaming || readyState !== 'open') return

    // Add user message
    addMessage({
      id: generateId(),
      role: 'user',
      content: query,
      timestamp: Date.now(),
    })

    // Add empty assistant placeholder for streaming
    addMessage({
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isStreaming: true,
    })

    resetBuffer()
    setStreaming(true)
    send({ query, session_id: sessionId })
    setInputValue('')
  }, [inputValue, isStreaming, readyState, addMessage, resetBuffer, setStreaming, send, sessionId])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const isConnected = readyState === 'open'

  return (
    <div className="flex flex-col h-full bg-bg-dark">
      {/* Connection status */}
      <div
        className={`flex items-center gap-2 px-4 py-1.5 text-xs border-b shrink-0
          ${isConnected
            ? 'bg-green-900/30 border-green-800 text-green-400'
            : 'bg-red-900/30 border-red-800 text-red-400'}`}
      >
        {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
        <span>
          {isConnected
            ? 'Connected'
            : readyState === 'connecting'
            ? 'Connecting...'
            : 'Disconnected — backend may still be starting'}
        </span>
        {!isConnected && (
          <button
            onClick={reconnect}
            className="ml-auto flex items-center gap-1 hover:text-red-200 transition-colors"
            aria-label="Reconnect"
          >
            <RefreshCw size={11} />
            <span>Retry</span>
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 opacity-60">
            <span className="text-4xl">🔴</span>
            <p className="font-pixel text-pikachu-yellow text-xs">Pokédex Arcana</p>
            <p className="font-body text-gray-400 text-sm max-w-xs">
              Ask me anything about Pokémon — stats, lore, damage calculations, team building, and more.
            </p>
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

      {/* Input */}
      <div className="px-4 py-3 border-t border-bg-panel bg-bg-panel shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isConnected ? 'Ask about a Pokémon...' : 'Waiting for connection...'}
            rows={1}
            disabled={isStreaming || !isConnected}
            className="flex-1 resize-none bg-bg-dark border border-gray-600 rounded-xl px-4 py-2.5 text-text-light text-sm font-body placeholder-gray-500 focus:outline-none focus:border-pikachu-yellow transition-colors disabled:opacity-50 max-h-32 overflow-y-auto"
            style={{ minHeight: '42px' }}
            aria-label="Chat input"
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming || !isConnected}
            className="shrink-0 w-10 h-10 rounded-xl bg-pokedex-red hover:bg-pokedex-red-dark disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
            aria-label="Send message"
          >
            <Send size={16} className="text-white" />
          </button>
        </div>
        <p className="text-[10px] text-gray-600 mt-1 text-right">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}

export default ChatPanel
