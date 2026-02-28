import { Component, type ErrorInfo, type ReactNode } from "react";
import { logTelemetry } from "@/lib/telemetry";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = { hasError: false };

  public static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Unhandled UI error", error, errorInfo);
    logTelemetry("ui.error_boundary", {
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
  }

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-center">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Something went wrong</h1>
            <p className="mt-3 text-slate-600">Please refresh the page or try again in a moment.</p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
