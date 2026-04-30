import { useRef, useCallback, useState } from 'react'

interface StreamBufferOptions {
  /** Called with accumulated text on each flush. Optional. */
  onFlush?: (text: string) => void
  flushIntervalMs?: number
}

interface UseStreamBufferReturn {
  streamedText: string
  push: (token: string) => void
  flush: () => void
  reset: () => void
}

/**
 * Buffers incoming token strings, accumulates them, and exposes the current
 * streamed text. Flushes periodically to avoid excessive re-renders.
 *
 * Works both with and without an onFlush callback.
 */
export function useStreamBuffer({
  onFlush,
  flushIntervalMs = 50,
}: StreamBufferOptions = {}): UseStreamBufferReturn {
  const bufferRef = useRef<string[]>([])
  const accumulatedRef = useRef<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onFlushRef = useRef(onFlush)
  onFlushRef.current = onFlush

  const [streamedText, setStreamedText] = useState<string>('')

  const flush = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (bufferRef.current.length > 0) {
      const chunk = bufferRef.current.join('')
      bufferRef.current = []
      accumulatedRef.current += chunk
      setStreamedText(accumulatedRef.current)
      onFlushRef.current?.(accumulatedRef.current)
    }
  }, [])

  const push = useCallback(
    (token: string) => {
      bufferRef.current.push(token)
      if (!timerRef.current) {
        timerRef.current = setTimeout(() => {
          timerRef.current = null
          flush()
        }, flushIntervalMs)
      }
    },
    [flush, flushIntervalMs],
  )

  const reset = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    bufferRef.current = []
    accumulatedRef.current = ''
    setStreamedText('')
  }, [])

  return { streamedText, push, flush, reset }
}
