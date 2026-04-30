import { useEffect, useRef, useCallback, useState } from 'react'

export type WSReadyState = 'connecting' | 'open' | 'closed' | 'error'

export interface ServerEvent {
  event: 'token' | 'agent_activity' | 'citation' | 'error' | 'done'
  data: unknown
  event_index?: number
}

interface UseWebSocketOptions {
  sessionId: string
  onEvent: (event: ServerEvent) => void
  enabled?: boolean
}

interface UseWebSocketReturn {
  readyState: WSReadyState
  send: (data: unknown) => void
  disconnect: () => void
  reconnect: () => void
  lastEventIndex: number
}

const WS_BASE = import.meta.env.VITE_WS_URL ?? ''

// Derive the backend WebSocket URL.
// In production (served as static files), the frontend and backend run on
// different ports, so we must point directly at the backend port.
// VITE_WS_URL overrides everything (e.g. "ws://localhost:8080").
function getWsBase(): string {
  if (WS_BASE) return WS_BASE
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const hostname = window.location.hostname
  // Default: backend is always on port 8080
  return `${protocol}://${hostname}:8080`
}

export function useWebSocket({
  sessionId,
  onEvent,
  enabled = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const lastEventIndexRef = useRef<number>(-1)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const [readyState, setReadyState] = useState<WSReadyState>('closed')
  const [lastEventIndex, setLastEventIndex] = useState<number>(-1)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return

    const host = getWsBase()
    const url = `${host}/ws/${sessionId}?last_event_index=${lastEventIndexRef.current}`

    setReadyState('connecting')
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setReadyState('open')
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return
      try {
        const parsed: ServerEvent = JSON.parse(evt.data as string)
        if (parsed.event_index !== undefined) {
          lastEventIndexRef.current = parsed.event_index
          setLastEventIndex(parsed.event_index)
        }
        onEventRef.current(parsed)
      } catch {
        // ignore malformed messages
      }
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setReadyState('error')
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setReadyState('closed')
      wsRef.current = null
      // Auto-reconnect after 2s
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current && enabled) connect()
      }, 2000)
    }
  }, [sessionId, enabled])

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  const reconnect = useCallback(() => {
    disconnect()
    connect()
  }, [disconnect, connect])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()
    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [connect, disconnect, enabled])

  return { readyState, send, disconnect, reconnect, lastEventIndex }
}
