import React from 'react'
import { Citation } from '../../store/sessionStore'
import CitationLink from '../ui/CitationLink'
import VerificationBadge from '../ui/VerificationBadge'
import StreamingCursor from './StreamingCursor'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  verified?: boolean
  discrepancyDetected?: boolean
  agentValue?: number | string
  referenceValue?: number | string
  isStreaming?: boolean
  agentName?: string
  timestamp?: number
  id?: string
}

// Agent icon map
const AGENT_ICONS: Record<string, string> = {
  'Stats Agent': '📊',
  'Damage Calc Agent': '⚔️',
  'Lore Agent': '📖',
  'Team Builder Agent': '🏆',
  'Verification Agent': '✅',
  'Report Agent': '📄',
  'DataViz Agent': '📈',
  'Orchestrator': '🧠',
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  role, content, citations, verified, discrepancyDetected,
  agentValue, referenceValue, isStreaming, agentName, timestamp, id,
}) => {
  const isUser = role === 'user'
  const agentIcon = agentName ? (AGENT_ICONS[agentName] ?? '🤖') : null

  return (
    <div
      className={`flex w-full mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}
      data-message-id={id}
    >
      {/* Assistant avatar */}
      {!isUser && (
        <div
          className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center mr-2 mt-1 text-sm"
          style={{
            background: 'linear-gradient(135deg, #1e3a5f, #0f2040)',
            border: '1px solid rgba(59,130,246,0.3)',
            boxShadow: '0 0 10px rgba(59,130,246,0.2)',
          }}
        >
          {agentIcon ?? '🔴'}
        </div>
      )}

      <div className={`max-w-[80%] md:max-w-[75%] ${isUser ? '' : 'flex-1'}`}>
        {/* Agent label */}
        {!isUser && agentName && (
          <p
            className="text-[9px] font-pixel mb-1 ml-1"
            style={{ color: 'rgba(147,197,253,0.6)' }}
          >
            {agentName.toUpperCase()}
          </p>
        )}

        {/* Bubble */}
        <div
          className="rounded-2xl px-4 py-3 shadow-lg"
          style={isUser ? {
            background: 'linear-gradient(135deg, #FFCB05, #f59e0b)',
            color: '#111827',
            borderBottomRightRadius: '4px',
            boxShadow: '0 4px 20px rgba(255,203,5,0.3)',
          } : {
            background: 'linear-gradient(135deg, rgba(30,58,95,0.9), rgba(15,32,64,0.95))',
            color: '#e2e8f0',
            borderBottomLeftRadius: '4px',
            border: '1px solid rgba(59,130,246,0.2)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
          }}
        >
          {/* Content */}
          <div
            className="font-body text-sm leading-relaxed whitespace-pre-wrap break-words"
            style={{ fontSize: '13.5px' }}
          >
            {content}
            {isStreaming && <StreamingCursor />}
          </div>

          {/* Citations */}
          {citations && citations.length > 0 && (
            <div
              className="flex flex-wrap gap-1 mt-2 pt-2"
              style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}
            >
              <span className="text-[10px] mr-1" style={{ color: 'rgba(147,197,253,0.7)' }}>
                📚 Sources:
              </span>
              {citations.map((citation, idx) => (
                <CitationLink
                  key={`${citation.documentId}-${idx}`}
                  citation={citation}
                  index={idx}
                />
              ))}
            </div>
          )}

          {/* Verification badge */}
          {(verified !== undefined || discrepancyDetected !== undefined) && (
            <div className="mt-1.5 flex justify-end">
              <VerificationBadge
                verified={verified ?? false}
                discrepancyDetected={discrepancyDetected ?? false}
                agentValue={agentValue}
                referenceValue={referenceValue}
              />
            </div>
          )}
        </div>

        {/* Timestamp */}
        {timestamp && (
          <p
            className={`text-[9px] mt-1 font-body ${isUser ? 'text-right mr-1' : 'ml-1'}`}
            style={{ color: 'rgba(148,163,184,0.4)' }}
          >
            {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center ml-2 mt-1 text-sm font-pixel"
          style={{
            background: 'linear-gradient(135deg, #FFCB05, #f59e0b)',
            color: '#111',
            fontSize: '10px',
            boxShadow: '0 0 10px rgba(255,203,5,0.3)',
          }}
        >
          TR
        </div>
      )}
    </div>
  )
}

export default MessageBubble
