// SPDX-License-Identifier: AGPL-3.0-or-later
// A crash inside one app window stays in that window (the desktop keeps running).
import { Component, type ReactNode } from "react";

import { ErrorState } from "../components/Feedback.tsx";

export class WindowBoundary extends Component<
  { children: ReactNode; path: string },
  { error: unknown; failed: boolean }
> {
  state = { error: null as unknown, failed: false };

  static getDerivedStateFromError(error: unknown) {
    return { error, failed: true };
  }

  componentDidUpdate(previous: { path: string }) {
    // Navigating inside the window (another tab, another project) retries the page.
    if (previous.path !== this.props.path && this.state.failed)
      this.setState({ error: null, failed: false });
  }

  render() {
    if (this.state.failed)
      return (
        <ErrorState
          error={this.state.error}
          onRetry={() => this.setState({ error: null, failed: false })}
        />
      );
    return this.props.children;
  }
}
