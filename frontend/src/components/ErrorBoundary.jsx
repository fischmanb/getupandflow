import { Component } from "react";

/**
 * Catches render/runtime errors in the subtree and shows a recoverable fallback
 * instead of unmounting the whole app (which previously blanked the page).
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-fallback">
          <h3>Something went wrong here.</h3>
          <p className="subtle-copy">
            This part of the page hit an error. The rest of the app is still working.
          </p>
          <button className="task-create-button" onClick={this.handleReset} type="button">
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
