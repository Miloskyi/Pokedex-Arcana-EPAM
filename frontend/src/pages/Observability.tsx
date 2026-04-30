import React, { useEffect, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from 'recharts'
import { RefreshCw, AlertCircle } from 'lucide-react'

interface AgentSpan {
  agent_name: string
  latency_ms: number
  input_tokens: number
  output_tokens: number
}

interface QueryTrace {
  id: string
  query_text: string
  total_latency_ms: number
  slowest_agent: string
  agent_spans: AgentSpan[]
  token_count: number
  created_at: string
}

interface ObservabilityData {
  traces: QueryTrace[]
  total_queries: number
  avg_latency_ms: number
  total_tokens: number
  slow_queries: number
}

const API_BASE = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8080`

async function fetchObservability(): Promise<ObservabilityData> {
  const res = await fetch(`${API_BASE}/admin/observability`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<ObservabilityData>
}

const Observability: React.FC = () => {
  const [data, setData] = useState<ObservabilityData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchObservability()
      setData(result)
      setLastRefresh(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch observability data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const interval = setInterval(() => void load(), 30_000)
    return () => clearInterval(interval)
  }, [])

  const latencyChartData = data?.traces.slice(-20).map((t) => ({
    query: t.query_text.slice(0, 20) + '…',
    latency: t.total_latency_ms,
    tokens: t.token_count,
  })) ?? []

  const agentBreakdownData = (() => {
    if (!data?.traces.length) return []
    const agentMap: Record<string, { total: number; count: number }> = {}
    for (const trace of data.traces) {
      for (const span of trace.agent_spans ?? []) {
        if (!agentMap[span.agent_name]) agentMap[span.agent_name] = { total: 0, count: 0 }
        agentMap[span.agent_name].total += span.latency_ms
        agentMap[span.agent_name].count += 1
      }
    }
    return Object.entries(agentMap).map(([name, { total, count }]) => ({
      name: name.replace(/_agent/i, '').replace(/_/g, ' '),
      avgLatency: Math.round(total / count),
      calls: count,
    }))
  })()

  return (
    <div className="min-h-screen bg-bg-dark text-text-light">
      {/* Header */}
      <header className="px-6 py-4 bg-pokedex-red border-b-4 border-pokedex-red-dark flex items-center justify-between">
        <h1 className="font-pixel text-pikachu-yellow text-sm">Observability Dashboard</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-red-200 font-body">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-pokedex-red-dark hover:bg-red-900 rounded-lg text-white text-xs transition-colors disabled:opacity-50"
            aria-label="Refresh data"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {/* Error state */}
        {error && (
          <div className="flex items-center gap-2 p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Summary cards */}
        {data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Queries" value={data.total_queries.toLocaleString()} />
            <StatCard label="Avg Latency" value={`${data.avg_latency_ms.toLocaleString()} ms`} />
            <StatCard label="Total Tokens" value={data.total_tokens.toLocaleString()} />
            <StatCard
              label="Slow Queries (>10s)"
              value={data.slow_queries.toLocaleString()}
              highlight={data.slow_queries > 0}
            />
          </div>
        )}

        {/* Per-query latency chart */}
        {latencyChartData.length > 0 && (
          <div className="bg-bg-panel rounded-xl p-4">
            <h2 className="text-xs font-pixel text-pikachu-yellow mb-4">Per-Query Latency (last 20)</h2>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={latencyChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis dataKey="query" tick={{ fill: '#888', fontSize: 9 }} />
                <YAxis tick={{ fill: '#888', fontSize: 10 }} unit="ms" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#2D2D2D', border: '1px solid #444', borderRadius: 8 }}
                  labelStyle={{ color: '#F0F0F0' }}
                />
                <Legend wrapperStyle={{ color: '#F0F0F0', fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="latency"
                  stroke="#FFCB05"
                  strokeWidth={2}
                  dot={false}
                  name="Latency (ms)"
                />
                <Line
                  type="monotone"
                  dataKey="tokens"
                  stroke="#6890F0"
                  strokeWidth={2}
                  dot={false}
                  name="Tokens"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Agent trace breakdown */}
        {agentBreakdownData.length > 0 && (
          <div className="bg-bg-panel rounded-xl p-4">
            <h2 className="text-xs font-pixel text-pikachu-yellow mb-4">Agent Avg Latency Breakdown</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={agentBreakdownData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis dataKey="name" tick={{ fill: '#F0F0F0', fontSize: 10 }} />
                <YAxis tick={{ fill: '#888', fontSize: 10 }} unit="ms" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#2D2D2D', border: '1px solid #444', borderRadius: 8 }}
                  labelStyle={{ color: '#F0F0F0' }}
                />
                <Bar dataKey="avgLatency" fill="#CC0000" radius={[4, 4, 0, 0]} name="Avg Latency (ms)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Recent traces table */}
        {data && data.traces.length > 0 && (
          <div className="bg-bg-panel rounded-xl p-4 overflow-x-auto">
            <h2 className="text-xs font-pixel text-pikachu-yellow mb-4">Recent Query Traces</h2>
            <table className="w-full text-xs font-body border-collapse">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="text-left py-2 pr-4">Query</th>
                  <th className="text-right py-2 pr-4">Latency</th>
                  <th className="text-right py-2 pr-4">Tokens</th>
                  <th className="text-left py-2 pr-4">Slowest Agent</th>
                  <th className="text-right py-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.traces.slice(-10).reverse().map((trace) => (
                  <tr key={trace.id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                    <td className="py-2 pr-4 max-w-[200px] truncate text-text-light">
                      {trace.query_text}
                    </td>
                    <td className={`py-2 pr-4 text-right font-mono ${trace.total_latency_ms > 10000 ? 'text-red-400' : 'text-green-400'}`}>
                      {trace.total_latency_ms.toLocaleString()} ms
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-blue-300">
                      {trace.token_count.toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-gray-400 capitalize">
                      {trace.slowest_agent?.replace(/_/g, ' ') ?? '—'}
                    </td>
                    <td className="py-2 text-right text-gray-500">
                      {new Date(trace.created_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && data?.traces.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <p className="text-4xl mb-3">📊</p>
            <p className="font-body">No query traces yet. Start chatting to generate data.</p>
          </div>
        )}
      </div>
    </div>
  )
}

interface StatCardProps {
  label: string
  value: string
  highlight?: boolean
}

const StatCard: React.FC<StatCardProps> = ({ label, value, highlight = false }) => (
  <div className={`bg-bg-panel rounded-xl p-4 border ${highlight ? 'border-red-600' : 'border-gray-700'}`}>
    <p className="text-xs text-gray-400 font-body mb-1">{label}</p>
    <p className={`text-xl font-pixel ${highlight ? 'text-red-400' : 'text-pikachu-yellow'}`}>
      {value}
    </p>
  </div>
)

export default Observability
