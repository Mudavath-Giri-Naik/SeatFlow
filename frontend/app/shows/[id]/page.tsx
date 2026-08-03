"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Header } from "@/components/Header";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast-context";
import { api, ApiError, Seat, SeatStatus, Show, WS_URL } from "@/lib/api";
import { formatCountdown, formatDateTime, formatPrice } from "@/lib/format";

// Must match the backend's SEAT_HOLD_TTL_SECONDS (see .env.example). There's
// no expires_at on the Booking response, so we track it client-side from the
// moment our own hold call succeeds.
const HOLD_TTL_SECONDS = 120;

type SeatEvent = { event: "held" | "booked" | "released"; seat_id: string; status: SeatStatus };
type MyHold = { bookingId: string; expiresAt: number };

export default function SeatMapPage() {
  const params = useParams<{ id: string }>();
  const showId = params.id;
  const { token, loading: authLoading } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const [show, setShow] = useState<Show | null>(null);
  const [seats, setSeats] = useState<Seat[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [myHolds, setMyHolds] = useState<Map<string, MyHold>>(new Map());
  const [myBookings, setMyBookings] = useState<Map<string, string>>(new Map()); // seatId -> bookingId
  const [busySeats, setBusySeats] = useState<Set<string>>(new Set());
  const [now, setNow] = useState(Date.now());

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!token) router.replace("/login");
  }, [authLoading, token, router]);

  const loadSeats = useCallback(() => {
    api
      .getSeats(showId)
      .then(setSeats)
      .catch(() => setError("Couldn't load the seat map."));
  }, [showId]);

  useEffect(() => {
    api
      .getShow(showId)
      .then(setShow)
      .catch(() => setError("Show not found."));
    loadSeats();
  }, [showId, loadSeats]);

  // Live updates over WebSocket, backed by Redis Pub/Sub server-side.
  useEffect(() => {
    setWsStatus("connecting");
    const ws = new WebSocket(`${WS_URL}/ws/shows/${showId}`);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("disconnected");
    ws.onmessage = (msg) => {
      try {
        const evt: SeatEvent = JSON.parse(msg.data);
        setSeats((prev) => (prev ? prev.map((s) => (s.id === evt.seat_id ? { ...s, status: evt.status } : s)) : prev));
      } catch {
        // ignore malformed frames
      }
    };

    return () => ws.close();
  }, [showId]);

  // Fallback resync every 30s in case a WS event was missed (e.g. brief disconnect).
  useEffect(() => {
    const id = window.setInterval(loadSeats, 30000);
    return () => window.clearInterval(id);
  }, [loadSeats]);

  // Countdown tick + local hold-expiry handling.
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    for (const [seatId, hold] of myHolds) {
      if (hold.expiresAt <= now) {
        setMyHolds((prev) => {
          const next = new Map(prev);
          next.delete(seatId);
          return next;
        });
        setSeats((prev) => (prev ? prev.map((s) => (s.id === seatId ? { ...s, status: "available" } : s)) : prev));
        toast.push("info", "Your hold expired — seat released.");
      }
    }
  }, [now, myHolds, toast]);

  const seatsByRow = useMemo(() => {
    if (!seats) return [];
    const rows = new Map<string, Seat[]>();
    for (const seat of seats) {
      if (!rows.has(seat.row_label)) rows.set(seat.row_label, []);
      rows.get(seat.row_label)!.push(seat);
    }
    return Array.from(rows.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([label, rowSeats]) => [label, rowSeats.sort((a, b) => a.seat_number - b.seat_number)] as const);
  }, [seats]);

  function toggleSelect(seat: Seat) {
    if (seat.status !== "available" || myHolds.has(seat.id)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(seat.id)) next.delete(seat.id);
      else next.add(seat.id);
      return next;
    });
  }

  async function holdSelected() {
    if (!token || selected.size === 0) return;
    const seatIds = Array.from(selected);
    setBusySeats((prev) => new Set([...prev, ...seatIds]));

    const results = await Promise.allSettled(seatIds.map((id) => api.holdSeat(id, token)));

    const newHolds = new Map(myHolds);
    let successCount = 0;
    results.forEach((result, i) => {
      const seatId = seatIds[i];
      if (result.status === "fulfilled") {
        newHolds.set(seatId, { bookingId: result.value.id, expiresAt: Date.now() + HOLD_TTL_SECONDS * 1000 });
        successCount++;
      } else {
        const msg = result.reason instanceof ApiError ? result.reason.message : "Could not hold this seat.";
        toast.push("error", msg);
      }
    });

    setMyHolds(newHolds);
    setSelected(new Set());
    setBusySeats((prev) => {
      const next = new Set(prev);
      seatIds.forEach((id) => next.delete(id));
      return next;
    });
    if (successCount > 0) {
      toast.push("success", `Held ${successCount} seat${successCount > 1 ? "s" : ""} — you have ${HOLD_TTL_SECONDS / 60} minutes to confirm.`);
      loadSeats();
    }
  }

  async function confirmHeld() {
    if (!token || myHolds.size === 0) return;
    const seatIds = Array.from(myHolds.keys());
    setBusySeats((prev) => new Set([...prev, ...seatIds]));

    const results = await Promise.allSettled(
      seatIds.map((id) => api.confirmBooking(id, token, crypto.randomUUID()))
    );

    const newHolds = new Map(myHolds);
    const newBookings = new Map(myBookings);
    let successCount = 0;
    results.forEach((result, i) => {
      const seatId = seatIds[i];
      if (result.status === "fulfilled") {
        newHolds.delete(seatId);
        newBookings.set(seatId, result.value.id);
        setSeats((prev) => (prev ? prev.map((s) => (s.id === seatId ? { ...s, status: "booked" } : s)) : prev));
        successCount++;
      } else {
        const msg = result.reason instanceof ApiError ? result.reason.message : "Payment failed — please retry.";
        toast.push("error", msg);
      }
    });

    setMyHolds(newHolds);
    setMyBookings(newBookings);
    setBusySeats((prev) => {
      const next = new Set(prev);
      seatIds.forEach((id) => next.delete(id));
      return next;
    });
    if (successCount > 0) {
      toast.push("success", `Booked ${successCount} seat${successCount > 1 ? "s" : ""}! Enjoy the show.`);
    }
  }

  async function releaseHeld(seatId: string) {
    if (!token) return;
    const hold = myHolds.get(seatId);
    if (!hold) return;
    setBusySeats((prev) => new Set(prev).add(seatId));
    try {
      await api.cancelBooking(hold.bookingId, token);
      setMyHolds((prev) => {
        const next = new Map(prev);
        next.delete(seatId);
        return next;
      });
      setSeats((prev) => (prev ? prev.map((s) => (s.id === seatId ? { ...s, status: "available" } : s)) : prev));
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Couldn't release this seat.");
    } finally {
      setBusySeats((prev) => {
        const next = new Set(prev);
        next.delete(seatId);
        return next;
      });
    }
  }

  async function cancelBooked(seatId: string) {
    if (!token) return;
    const bookingId = myBookings.get(seatId);
    if (!bookingId) return;
    setBusySeats((prev) => new Set(prev).add(seatId));
    try {
      await api.cancelBooking(bookingId, token);
      setMyBookings((prev) => {
        const next = new Map(prev);
        next.delete(seatId);
        return next;
      });
      setSeats((prev) => (prev ? prev.map((s) => (s.id === seatId ? { ...s, status: "available" } : s)) : prev));
      toast.push("info", "Booking cancelled.");
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Couldn't cancel this booking.");
    } finally {
      setBusySeats((prev) => {
        const next = new Set(prev);
        next.delete(seatId);
        return next;
      });
    }
  }

  function seatClass(seat: Seat): string {
    if (myBookings.has(seat.id)) return "seat seat-mine-booked";
    if (myHolds.has(seat.id)) return "seat seat-mine-held";
    if (selected.has(seat.id)) return "seat seat-selected";
    if (seat.status === "booked") return "seat seat-booked-other";
    if (seat.status === "held") return "seat seat-held-other";
    return "seat seat-available";
  }

  const selectedTotal = useMemo(() => {
    if (!seats) return 0;
    return seats.filter((s) => selected.has(s.id)).reduce((sum, s) => sum + parseFloat(s.price), 0);
  }, [seats, selected]);

  const heldSeats = useMemo(() => (seats ?? []).filter((s) => myHolds.has(s.id)), [seats, myHolds]);

  if (authLoading || !token) {
    return (
      <div className="full-screen-center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="page">
      <Header backHref="/shows" backLabel="All shows" />
      <main className="container">
        {error && <p className="form-error">{error}</p>}

        {show && (
          <div className="page-heading">
            <h1>{show.title}</h1>
            <p className="muted">
              {show.venue.name}
              {show.venue.city ? ` · ${show.venue.city}` : ""} · {formatDateTime(show.starts_at)}
            </p>
            <span className={`ws-badge ws-${wsStatus}`}>
              <span className="ws-dot" /> {wsStatus === "connected" ? "Live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
            </span>
          </div>
        )}

        {seats === null && !error && (
          <div className="theater">
            <div className="stage skeleton" />
          </div>
        )}

        {seats !== null && (
          <div className="theater">
            <div className="stage">STAGE</div>

            <div className="seat-rows">
              {seatsByRow.map(([rowLabel, rowSeats]) => (
                <div key={rowLabel} className="seat-row">
                  <span className="row-label">{rowLabel}</span>
                  <div className="row-seats">
                    {rowSeats.map((seat) => {
                      const isBusy = busySeats.has(seat.id);
                      const isDisabled =
                        isBusy ||
                        (seat.status !== "available" && !myHolds.has(seat.id) && !myBookings.has(seat.id));
                      return (
                        <button
                          key={seat.id}
                          type="button"
                          className={seatClass(seat)}
                          disabled={isDisabled}
                          title={
                            myBookings.has(seat.id)
                              ? `${rowLabel}${seat.seat_number} · booked by you · click to cancel`
                              : `${rowLabel}${seat.seat_number} · ${formatPrice(seat.price)} · ${seat.status}`
                          }
                          onClick={() => {
                            if (myBookings.has(seat.id)) {
                              if (window.confirm(`Cancel your booking for seat ${rowLabel}${seat.seat_number}?`)) {
                                cancelBooked(seat.id);
                              }
                              return;
                            }
                            toggleSelect(seat);
                          }}
                        >
                          {seat.seat_number}
                        </button>
                      );
                    })}
                  </div>
                  <span className="row-label">{rowLabel}</span>
                </div>
              ))}
            </div>

            <div className="legend">
              <span className="legend-item"><i className="seat seat-available legend-swatch" />Available</span>
              <span className="legend-item"><i className="seat seat-selected legend-swatch" />Selected</span>
              <span className="legend-item"><i className="seat seat-mine-held legend-swatch" />Your hold</span>
              <span className="legend-item"><i className="seat seat-held-other legend-swatch" />Held</span>
              <span className="legend-item"><i className="seat seat-booked-other legend-swatch" />Booked</span>
              <span className="legend-item"><i className="seat seat-mine-booked legend-swatch" />Your booking</span>
            </div>
          </div>
        )}
      </main>

      {(selected.size > 0 || heldSeats.length > 0) && (
        <div className="action-bar">
          <div className="action-bar-inner">
            {heldSeats.length === 0 ? (
              <>
                <div className="action-summary">
                  <strong>{selected.size} seat{selected.size > 1 ? "s" : ""}</strong> selected
                  <span className="muted"> · {formatPrice(selectedTotal)}</span>
                </div>
                <button className="btn btn-primary" onClick={holdSelected} disabled={busySeats.size > 0}>
                  {busySeats.size > 0 ? "Holding…" : "Hold Seats"}
                </button>
              </>
            ) : (
              <>
                <div className="action-summary held-summary">
                  {heldSeats.map((seat) => {
                    const hold = myHolds.get(seat.id)!;
                    const remaining = Math.max(0, Math.round((hold.expiresAt - now) / 1000));
                    return (
                      <span key={seat.id} className="held-chip">
                        {seat.row_label}
                        {seat.seat_number}
                        <em>{formatCountdown(remaining)}</em>
                        <button
                          type="button"
                          className="held-chip-x"
                          onClick={() => releaseHeld(seat.id)}
                          disabled={busySeats.has(seat.id)}
                          aria-label={`Release seat ${seat.row_label}${seat.seat_number}`}
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
                <button className="btn btn-primary" onClick={confirmHeld} disabled={busySeats.size > 0}>
                  {busySeats.size > 0 ? "Processing…" : "Confirm & Pay"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
