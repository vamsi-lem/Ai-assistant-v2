import { useEffect, useState } from 'react';

import { ApiError, createLead, getHealth } from './api/client';
import { CallPanel } from './components/CallPanel';
import { LeadForm } from './components/LeadForm';
import type { BrowserJoin, Call, LeadInput } from './types';

export default function App() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string | null>(null);
  const [call, setCall] = useState<Call | null>(null);
  const [join, setJoin] = useState<BrowserJoin | null>(null);
  const [health, setHealth] = useState<Record<string, string> | null>(null);

  // Read the backend's own account of itself once at load. Cheaper than
  // discovering a misconfiguration halfway through a submission.
  useEffect(() => {
    void getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function handleSubmit(input: LeadInput) {
    setBusy(true);
    setError(null);
    setSkipped(null);

    try {
      const result = await createLead(input);
      setSkipped(result.call_skipped_reason);

      if (result.call) {
        setCall(result.call);
        setJoin(result.join);
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Something went wrong. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setCall(null);
    setJoin(null);
    setError(null);
    setSkipped(null);
  }

  return (
    <div className="page">
      <header>
        <p className="eyebrow">Lemniscate Growth</p>
        <h1>Talk to Maya</h1>
        <p className="lede">
          Submit your enquiry and our AI assistant will call you straight away to
          understand what you need and arrange a counsellor.
        </p>
      </header>

      {error && (
        <div className="notice notice-bad">
          <strong>Could not submit</strong>
          <pre>{error}</pre>
        </div>
      )}

      {skipped && !call && (
        <div className="notice">
          <strong>Saved, but not called</strong>
          <p>{skipped}</p>
          <button type="button" className="ghost" onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {skipped && call && (
        <div className="notice notice-bad">
          <strong>Your details are saved, but the call did not go through</strong>
          <p>{skipped}</p>
        </div>
      )}

      {call ? (
        <CallPanel call={call} join={join} onReset={reset} />
      ) : (
        !skipped && <LeadForm onSubmit={handleSubmit} busy={busy} />
      )}

      <footer>
        {health ? (
          <span className="mono">
            backend {health.status} &middot; db {health.database} &middot;{' '}
            {health.transport}
          </span>
        ) : (
          <span className="mono muted">backend unreachable</span>
        )}
      </footer>
    </div>
  );
}
