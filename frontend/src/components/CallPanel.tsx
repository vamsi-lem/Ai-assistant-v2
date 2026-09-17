/**
 * The live call.
 *
 * On the browser path this joins the LiveKit room with the token the backend
 * minted, unlocks audio, and shows what is happening. On the phone path there
 * is nothing to join here, so it just reports status while the carrier does
 * its work.
 *
 * The one non-obvious thing: browsers block autoplaying audio until the user
 * has interacted with the page. room.startAudio() is what releases it. Without
 * that call the connection succeeds, the agent speaks, and the lead hears
 * nothing at all.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';

import { getCallStatus } from '../api/client';
import type { BrowserJoin, Call, CallStatusResponse } from '../types';

type Phase =
  | 'connecting'
  | 'needs-audio-unlock'
  | 'live'
  | 'ended'
  | 'error';

interface Props {
  call: Call;
  join: BrowserJoin | null;
  onReset: () => void;
}

const TERMINAL = new Set(['completed', 'failed', 'no-answer', 'busy']);

export function CallPanel({ call, join, onReset }: Props) {
  const [phase, setPhase] = useState<Phase>('connecting');
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CallStatusResponse | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const roomRef = useRef<Room | null>(null);

  // -- browser path: join the room ----------------------------------------

  useEffect(() => {
    if (!join) {
      // Phone path. Nothing to join; the carrier is dialling.
      setPhase('live');
      return;
    }

    let cancelled = false;
    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        // Attaching creates an <audio> element the browser may still refuse to
        // play until startAudio() has been allowed.
        const element = track.attach();
        element.style.display = 'none';
        document.body.appendChild(element);
      }
    });

    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (cancelled) return;
      setPhase(room.canPlaybackAudio ? 'live' : 'needs-audio-unlock');
    });

    room.on(RoomEvent.Disconnected, () => {
      if (!cancelled) setPhase('ended');
    });

    (async () => {
      try {
        await room.connect(join.url, join.token);
        // Publishing the mic is what lets the agent hear the lead.
        await room.localParticipant.setMicrophoneEnabled(true);

        if (cancelled) return;
        setPhase(room.canPlaybackAudio ? 'live' : 'needs-audio-unlock');
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : 'Could not connect to the call. Check your microphone permission.',
        );
        setPhase('error');
      }
    })();

    return () => {
      cancelled = true;
      void room.disconnect();
      roomRef.current = null;
    };
  }, [join]);

  // -- poll backend status -------------------------------------------------

  useEffect(() => {
    let stop = false;

    async function poll() {
      try {
        const next = await getCallStatus(call.id);
        if (stop) return;
        setStatus(next);
        if (TERMINAL.has(next.call.status)) setPhase('ended');
      } catch {
        // A failed poll is not worth interrupting a live call over.
      }
    }

    void poll();
    const timer = setInterval(poll, 3000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [call.id]);

  // -- elapsed timer -------------------------------------------------------

  useEffect(() => {
    if (phase === 'ended' || phase === 'error') return;
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const unlockAudio = useCallback(async () => {
    try {
      await roomRef.current?.startAudio();
      setPhase('live');
    } catch {
      setError('Your browser would not let us play audio. Try clicking again.');
    }
  }, []);

  const hangUp = useCallback(async () => {
    await roomRef.current?.disconnect();
    setPhase('ended');
  }, []);

  const minutes = Math.floor(elapsed / 60);
  const seconds = String(elapsed % 60).padStart(2, '0');

  return (
    <div className="card">
      <div className="call-head">
        <span className={`dot dot-${phase}`} aria-hidden="true" />
        <div>
          <h2>
            {phase === 'connecting' && 'Connecting…'}
            {phase === 'needs-audio-unlock' && 'One more tap'}
            {phase === 'live' && (join ? 'You are talking to Maya' : 'Calling your mobile')}
            {phase === 'ended' && 'Call ended'}
            {phase === 'error' && 'Could not connect'}
          </h2>
          <p className="muted">
            {join ? 'Browser call, no phone network involved' : 'Phone call via carrier'}
            {phase === 'live' && ` · ${minutes}:${seconds}`}
          </p>
        </div>
      </div>

      {phase === 'needs-audio-unlock' && (
        <div className="notice">
          <p>
            Your browser blocks sound until you interact with the page. Maya is
            already on the line.
          </p>
          <button type="button" onClick={unlockAudio}>
            Turn on sound
          </button>
        </div>
      )}

      {phase === 'error' && (
        <div className="notice notice-bad">
          <p>{error}</p>
        </div>
      )}

      {status?.call.error && (
        <div className="notice notice-bad">
          <p>{status.call.error}</p>
        </div>
      )}

      <dl className="facts">
        <div>
          <dt>Status</dt>
          <dd>{status?.call.status ?? call.status}</dd>
        </div>
        <div>
          <dt>Turns recorded</dt>
          <dd>{status?.turns ?? 0}</dd>
        </div>
        <div>
          <dt>Room</dt>
          <dd className="mono">{call.room_name ?? 'n/a'}</dd>
        </div>
      </dl>

      {status?.summary && (
        <div className="summary">
          <h3>Call summary</h3>
          <pre>{status.summary}</pre>
        </div>
      )}

      <div className="actions">
        {join && phase === 'live' && (
          <button type="button" className="ghost" onClick={hangUp}>
            Hang up
          </button>
        )}
        {(phase === 'ended' || phase === 'error') && (
          <button type="button" onClick={onReset}>
            Start another
          </button>
        )}
      </div>

      {phase === 'ended' && (status?.turns ?? 0) > 0 && (
        <p className="hint center">
          The full transcript is in the <code>conversations</code> table in Supabase.
        </p>
      )}
    </div>
  );
}
