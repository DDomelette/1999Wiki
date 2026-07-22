import { Component, type ErrorInfo, type ReactNode } from 'react'

interface WikiErrorBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  resetKey: string
}

interface WikiErrorBoundaryState {
  failed: boolean
}

export class WikiErrorBoundary extends Component<WikiErrorBoundaryProps, WikiErrorBoundaryState> {
  state: WikiErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): WikiErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[WikiErrorBoundary] Wiki 局部渲染失败', error, info)
  }

  componentDidUpdate(previous: WikiErrorBoundaryProps): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false })
    }
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
