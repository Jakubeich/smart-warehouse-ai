import { Component, type ReactNode } from "react";

/** Can wrap either DOM or R3F content; the caller supplies a matching fallback. */
export class RenderBoundary extends Component<
  {
    children: ReactNode;
    fallback: ReactNode;
    onError?: (error: Error) => void;
  },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
