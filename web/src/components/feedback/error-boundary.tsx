import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Last-resort catch for render-time crashes — keeps a broken panel from
 * taking down the whole mission-planning UI mid-flight. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-canvas p-8 text-center">
          <AlertTriangle className="h-10 w-10 text-danger-500" />
          <div>
            <h1 className="text-lg font-semibold text-text-primary">Something went wrong</h1>
            <p className="mt-1 max-w-md text-sm text-text-secondary">
              {this.state.error.message || 'The interface hit an unexpected error.'}
            </p>
          </div>
          <Button variant="accent" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}
