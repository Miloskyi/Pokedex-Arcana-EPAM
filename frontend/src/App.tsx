import React, { Suspense, lazy, Component, ErrorInfo, ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

const Home = lazy(() => import('./pages/Home'))
const Observability = lazy(() => import('./pages/Observability'))

// ─── Error Boundary ───────────────────────────────────────────────────────────

interface EBState { hasError: boolean; error?: Error }

class ErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): EBState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('React Error Boundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen bg-bg-dark text-text-light gap-4 p-8">
          <span className="text-5xl">⚠️</span>
          <h1 className="font-pixel text-pokedex-red text-sm">Something went wrong</h1>
          <p className="font-body text-gray-400 text-sm text-center max-w-md">
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: undefined })}
            className="px-4 py-2 bg-pokedex-red hover:bg-pokedex-red-dark text-white rounded-lg text-sm font-body transition-colors"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ─── Loading fallback ─────────────────────────────────────────────────────────

const LoadingFallback: React.FC = () => (
  <div className="flex items-center justify-center h-screen bg-bg-dark">
    <div className="flex flex-col items-center gap-3">
      <span className="text-4xl animate-bounce">🔴</span>
      <p className="font-pixel text-pikachu-yellow text-xs animate-pulse">Loading...</p>
    </div>
  </div>
)

// ─── App ──────────────────────────────────────────────────────────────────────

const App: React.FC = () => (
  <ErrorBoundary>
    <BrowserRouter>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/admin/observability" element={<Observability />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  </ErrorBoundary>
)

export default App
