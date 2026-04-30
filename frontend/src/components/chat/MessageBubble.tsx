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
  // Legacy: accept full message object too
  message?: {
    id: string
    role: 'user' | 'assistant'
    content: string
    citations?: Citation[]
    verification?: {
      verified: boolean
      discrepancyDetected: boolean
      agentValue?: number | string
      referenceValue?: number | string
    }
    agentName?: string
    timestamp: number
    isStreaming?: boolean
  }
}

const MessageBubble: React.FC<MessageBubbleProps> = (props) => {
  // Support both flat props and legacy message object
  const role = props.message?.role ?? props.role
  const content = props.message?.content ?? props.content
  const citations = props.message?.citations ?? props.citations
  const verified = props.message?.verification?.verified ?? props.verified
  const discrepancyDetected = props.message?.verification?.discrepancyDetected ?? props.discrepancyDetected
  const agentValue = props.message?.verification?.agentValue ?? props.agentValue
  const referenceValue = props.message?.verification?.referenceValue ?? props.referenceValue
  const isStreaming = props.message?.isStreaming ?? props.isStreaming
  const agentName = props.message?.agentName ?? props.agentName
  const timestamp = props.message?.timestamp ?? props.timestamp

  const isUser = role === 'user'

  return (
    <div
      className={`flex w-full mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}
      data-message-id={props.message?.id ?? props.id}
    >
      <div
        className={`max-w-[80%] md:max-w-[70%] rounded-2xl px-4 py-3 shadow-md
          ${isUser
            ? 'rounded-br-sm'
            : 'rounded-bl-sm'
          }`}
        style={{
          backgroundColor: isUser ? '#FFCB05' : '#1E3A5F',
          color: isUser ? '#111827' : '#ffffff',
        }}
      >
        {/* Agent label */}
        {!isUser && agentName && (
          <p className="text-[10px] text-blue-300 font-pixel mb-1 opacity-80">
            {agentName}
          </p>
        )}

        {/* Message content */}
        <p className="font-body text-sm leading-relaxed whitespace-pre-wrap break-words">
          {content}
          {isStreaming && <StreamingCursor />}
        </p>

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-white/20">
            <span className="text-[10px] text-blue-300 mr-1">Sources:</span>
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

        {/* Timestamp */}
        {timestamp && (
          <p className={`text-[9px] mt-1 opacity-50 ${isUser ? 'text-right' : 'text-left'}`}>
            {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        )}
      </div>
    </div>
  )
}

export default MessageBubble
