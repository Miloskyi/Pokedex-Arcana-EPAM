import React from 'react'
import { AgentActivity } from '../../store/sessionStore'

interface AgentActivityBarProps {
  agents: AgentActivity[]
  className?: string
}

const AGENT_CONFIG: Record<string, { icon: string; color: string }> = {
  stats_agent:        { icon: '📊', color: '#60a5fa' },
  damage_calc_agent:  { icon: '⚔️', color: '#f87171' },
  lore_agent:         { icon: '📖', color: '#a78bfa' },
  team_builder_agent: { icon: '🏆', color: '#fbbf24' },
  verification_agent: { icon: '✅', color: '#34d399' },
  report_agent:       { icon: '📄', color: '#94a3b8' },
  dataviz_agent:      { icon: '📈', color: '#fb923c' },
  orchestrator:       { icon: '🧠', color: '#e879f9' },
}

function getConfig(name: string) {
  const key = name.toLowerCase().replace(/\s+/g, '_')
  return AGENT_CONFIG[key] ?? { icon: '🤖', color: '#60a5fa' }
}

const AgentActivityBar: React.FC<AgentActivityBarProps> = ({ agents }) => {
  const active = agents.filter(a => a.status === 'active')
  if (active.length === 0) return null

  return (
    <div
      className="shrink-0 flex items-center gap-2 px-4 py-2 overflow-x-auto"
      style={{
        background: 'linear-gradient(90deg, rgba(30,58,95,0.6), rgba(15,32,64,0.6))',
        borderTop: '1px solid rgba(59,130,246,0.15)',
        borderBottom: '1px solid rgba(59,130,246,0.1)',
      }}
      aria-live="polite"
    >
      <span className="text-[9px] font-pixel shrink-0" style={{ color: 'rgba(147,197,253,0.5)' }}>
        PROCESSING
      </span>

      {active.map(agent => {
        const cfg = getConfig(agent.agentName)
        return (
          <div
            key={agent.agentName}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full shrink-0"
            style={{
              background: `rgba(${hexToRgb(cfg.color)}, 0.1)`,
              border: `1px solid rgba(${hexToRgb(cfg.color)}, 0.3)`,
            }}
          >
            <span className="text-xs">{cfg.icon}</span>
            <span className="text-[10px] font-body" style={{ color: cfg.color }}>
              {agent.agentName}
            </span>
            {/* Animated dots */}
            <span className="flex gap-0.5 ml-0.5">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1 h-1 rounded-full"
                  style={{
                    background: cfg.color,
                    animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                    opacity: 0.7,
                  }}
                />
              ))}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `${r},${g},${b}`
}

export default AgentActivityBar
