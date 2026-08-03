"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

type Seat = {
  id: string;
  show_id: string;
  row_label: string;
  seat_number: number;
  price: string;
  status: "available" | "held" | "booked";
};

type SeatEvent = {
  event: "held" | "booked" | "released";
  seat_id: string;
  status: "available" | "held" | "booked";
};

export default function Home() {
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("password123");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [showId, setShowId] = useState("");
  const [seats, setSeats] = useState<Seat[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<"disconnected" | "connecting" | "connected">("disconnected");

  const wsRef = useRef<WebSocket | null>(null);

  const authHeaders = useCallback((): HeadersInit => {
    return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
  }, [accessToken]);

  async function signup() {
    setAuthError(null);
    try {
      const res = await fetch(`${API_URL}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok && res.status !== 409) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Signup failed (${res.status})`);
      }
      await login();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : String(err));
    }
  }

  async function login() {
    setAuthError(null);
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Login failed (${res.status})`);
      }
      const data = await res.json();
      setAccessToken(data.access_token);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : String(err));
    }
  }

  const loadSeats = useCallback(async () => {
    if (!showId) return;
    setActionError(null);
    try {
      const res = await fetch(`${API_URL}/shows/${showId}/seats`);
      if (!res.ok) throw new Error(`Failed to load seats (${res.status})`);
      const data: Seat[] = await res.json();
      setSeats(data);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, [showId]);

  useEffect(() => {
    if (!showId) return;
    loadSeats();

    setWsStatus("connecting");
    const ws = new WebSocket(`${WS_URL}/ws/shows/${showId}`);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("disconnected");
    ws.onmessage = (msg) => {
      try {
        const evt: SeatEvent = JSON.parse(msg.data);
        setSeats((prev) =>
          prev.map((s) => (s.id === evt.seat_id ? { ...s, status: evt.status } : s))
        );
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showId]);

  async function holdSeat(seatId: string) {
    setActionError(null);
    try {
      const res = await fetch(`${API_URL}/seats/${seatId}/hold`, {
        method: "POST",
        headers: { ...authHeaders() },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Hold failed (${res.status})`);
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function confirmSeat(seatId: string) {
    setActionError(null);
    try {
      const res = await fetch(`${API_URL}/bookings/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
          ...authHeaders(),
        },
        body: JSON.stringify({ seat_id: seatId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Confirm failed (${res.status})`);
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="container">
      <h1>SeatFlow</h1>
      <p className="status-line">Minimal frontend — proves the real-time booking backend works.</p>

      <div className="panel">
        <h3>1. Auth</h3>
        <div className="row">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password"
            type="password"
          />
          <button onClick={signup}>Sign Up</button>
          <button onClick={login}>Log In</button>
          <span className="status-line">{accessToken ? "Authenticated" : "Not authenticated"}</span>
        </div>
        {authError && <p className="error">{authError}</p>}
      </div>

      <div className="panel">
        <h3>2. Show</h3>
        <div className="row">
          <input
            value={showId}
            onChange={(e) => setShowId(e.target.value)}
            placeholder="show UUID (see scripts/seed.py output)"
            style={{ minWidth: 320 }}
          />
          <button onClick={loadSeats}>Load Seats</button>
          <span className="status-line">WS: {wsStatus}</span>
        </div>
      </div>

      <div className="panel">
        <h3>3. Seat map</h3>
        {actionError && <p className="error">{actionError}</p>}
        <div className="seat-grid">
          {seats.map((seat) => (
            <div key={seat.id} className={`seat seat-${seat.status}`}>
              <div>
                {seat.row_label}
                {seat.seat_number}
              </div>
              <div>${seat.price}</div>
              <div>{seat.status}</div>
              <div className="row" style={{ justifyContent: "center", marginTop: 4 }}>
                <button disabled={seat.status !== "available" || !accessToken} onClick={() => holdSeat(seat.id)}>
                  Hold
                </button>
                <button disabled={seat.status !== "held" || !accessToken} onClick={() => confirmSeat(seat.id)}>
                  Confirm
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
