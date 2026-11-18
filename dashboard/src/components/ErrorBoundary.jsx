import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    } else {
      window.location.hash = '#/app';
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-full min-h-[250px] flex flex-col items-center justify-center p-6 text-center space-y-4 bg-paper animate-fade">
          <div className="w-12 h-12 rounded-full bg-danger/10 text-danger flex items-center justify-center">
            <AlertCircle size={24} />
          </div>
          <div className="space-y-1 max-w-md">
            <h3 className="text-base font-medium text-ink">Something went wrong rendering this view</h3>
            <p className="text-xs text-muted leading-relaxed">
              {this.state.error?.message || "An unexpected error occurred while loading this section."}
            </p>
          </div>
          <button
            onClick={this.handleReset}
            className="btn-primary py-2 px-4 text-xs flex items-center gap-2"
          >
            <RefreshCw size={13} /> Return to Dashboard
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
