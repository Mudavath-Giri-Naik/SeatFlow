export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export type Venue = {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
  created_at: string;
};

export type Show = {
  id: string;
  venue_id: string;
  title: string;
  starts_at: string;
  created_at: string;
  venue: Venue;
};

export type SeatStatus = "available" | "held" | "booked";

export type Seat = {
  id: string;
  show_id: string;
  row_label: string;
  seat_number: number;
  price: string;
  status: SeatStatus;
};

export type BookingStatus = "held" | "confirmed" | "cancelled";

export type Booking = {
  id: string;
  seat_id: string;
  user_id: string;
  status: BookingStatus;
  held_at: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
};

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: HeadersInit = {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init.headers,
  };

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // response wasn't JSON, keep default message
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  signup: (email: string, password: string) =>
    request<User>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: (token: string) => request<User>("/auth/me", {}, token),

  listShows: () => request<Show[]>("/shows"),

  getShow: (showId: string) => request<Show>(`/shows/${showId}`),

  getSeats: (showId: string) => request<Seat[]>(`/shows/${showId}/seats`),

  holdSeat: (seatId: string, token: string) =>
    request<Booking>(`/seats/${seatId}/hold`, { method: "POST" }, token),

  confirmBooking: (seatId: string, token: string, idempotencyKey: string) =>
    request<Booking>(
      "/bookings/confirm",
      {
        method: "POST",
        body: JSON.stringify({ seat_id: seatId }),
        headers: { "Idempotency-Key": idempotencyKey },
      },
      token
    ),

  cancelBooking: (bookingId: string, token: string) =>
    request<Booking>(`/bookings/${bookingId}/cancel`, { method: "POST" }, token),
};
