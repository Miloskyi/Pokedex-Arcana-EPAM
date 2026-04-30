import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AgentActivity } from '../../store/sessionStore'

interface AgentActivityBarProps {
  agents: AgentActivity[]
  className?: string
}

const AGENT_LABELS: Record<string, string> = {
  stats_agent: 'Stats Agent',
  damage_calc_agent: 'Damage Calc Agent',
  lore_agent: 'Lore Agent',
  team_builder_agent: 'Team Builder Agent',
  verification_agent: 'Verification Agent',
  report_agent: 'Report Agent',
  dataviz_agent: 'DataViz Agent',
  orchestrator: 'Orchestrator',
}

function getAgentLabel(name: string): string {
  const key = name.toLowerCase().replace(/\s+/g, '_')
  return AGENT_LABELS[key] ?? name
}

const AnimatedDots: React.FC = () => (
  <span className="inline-flex gap-0.5 ml-0.5" aria-hidden="true">
    {[0, 1, 2].map((i) => (
      <motion.span
        key={i}
        className="inline-block w-1 h-1 rounded-full bg-blue-300"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
      />
    ))}
  </span>
)

const AgentActivityBar: React.FC<AgentActivityBarProps> = ({ agents, className = '' }) => {
  const activeAgents = agents.filter((a) => a.status === 'active')

  if (activeAgents.length === 0) return null

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 bg-screen-blue/80 border-t border-screen-blue text-xs ${className}`}
      aria-live="polite"
      aria-label="Active agents"
    >
      <AnimatePresence>
        {activeAgents.map((agent) => (
          <motion.span
            key={agent.agentName}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-center gap-1 text-blue-200 font-body"
          >
            <span>🔍 Consulting {getAgentLabel(agent.agentName)}...</span>
            <AnimatedDots />
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  )
}

export default AgentActivityBar
