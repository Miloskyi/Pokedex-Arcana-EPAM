import { create } from 'zustand'

export interface Citation {
  collection: string
  documentId: string
  passage: string
  sourceUrl?: string
}

export interface VerificationInfo {
  verified: boolean
  discrepancyDetected: boolean
  agentValue?: number | string
  referenceValue?: number | string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  verification?: VerificationInfo
  agentName?: string
  timestamp: number
  isStreaming?: boolean
}

export interface AgentActivity {
  agentName: string
  status: 'active' | 'done' | 'error'
  startedAt: number
}

interface SessionState {
  sessionId: string
  messages: ChatMessage[]
  activeAgents: AgentActivity[]
  isStreaming: boolean

  // Actions
  setSessionId: (id: string) => void
  addMessage: (msg: ChatMessage) => void
  appendToLastMessage: (text: string) => void
  finalizeLastMessage: () => void
  setActiveAgent: (agent: AgentActivity) => void
  setAgentActivity: (agent: AgentActivity) => void
  clearAgentActivity: () => void
  setStreaming: (streaming: boolean) => void
  resetSession: () => void
  reset: () => void
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: generateId(),
  messages: [],
  activeAgents: [],
  isStreaming: false,

  setSessionId: (id) => set({ sessionId: id }),

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  appendToLastMessage: (text) =>
    set((state) => {
      const msgs = [...state.messages]
      if (msgs.length === 0) return state
      const last = msgs[msgs.length - 1]
      msgs[msgs.length - 1] = { ...last, content: last.content + text, isStreaming: true }
      return { messages: msgs }
    }),

  finalizeLastMessage: () =>
    set((state) => {
      const msgs = [...state.messages]
      if (msgs.length === 0) return state
      const last = msgs[msgs.length - 1]
      msgs[msgs.length - 1] = { ...last, isStreaming: false }
      return { messages: msgs }
    }),

  setActiveAgent: (agent) =>
    set((state) => {
      const existing = state.activeAgents.findIndex((a) => a.agentName === agent.agentName)
      if (existing >= 0) {
        const updated = [...state.activeAgents]
        updated[existing] = agent
        return { activeAgents: updated }
      }
      return { activeAgents: [...state.activeAgents, agent] }
    }),

  setAgentActivity: (agent) =>
    set((state) => {
      const existing = state.activeAgents.findIndex((a) => a.agentName === agent.agentName)
      if (existing >= 0) {
        const updated = [...state.activeAgents]
        updated[existing] = agent
        return { activeAgents: updated }
      }
      return { activeAgents: [...state.activeAgents, agent] }
    }),

  clearAgentActivity: () => set({ activeAgents: [] }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  resetSession: () =>
    set({
      messages: [],
      activeAgents: [],
      isStreaming: false,
      sessionId: generateId(),
    }),

  reset: () =>
    set({
      messages: [],
      activeAgents: [],
      isStreaming: false,
      sessionId: generateId(),
    }),
}))

export { generateId }
