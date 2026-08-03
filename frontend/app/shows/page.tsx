"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/Header";
import { useAuth } from "@/lib/auth-context";
import { api, Show } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function ShowsPage() {
  const { token, loading: authLoading } = useAuth();
  const router = useRouter();

  const [shows, setShows] = useState<Show[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.replace("/login");
      return;
    }
  }, [authLoading, token, router]);

  useEffect(() => {
    api
      .listShows()
      .then(setShows)
      .catch(() => setError("Couldn't load shows. Is the backend running?"));
  }, []);

  if (authLoading || !token) {
    return (
      <div className="full-screen-center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="page">
      <Header />
      <main className="container">
        <div className="page-heading">
          <h1>Upcoming shows</h1>
          <p className="muted">Pick a show, then grab a seat before someone else does.</p>
        </div>

        {error && <p className="form-error">{error}</p>}

        {shows === null && !error && (
          <div className="show-grid">
            {[1, 2, 3].map((i) => (
              <div key={i} className="show-card skeleton" />
            ))}
          </div>
        )}

        {shows !== null && shows.length === 0 && (
          <div className="empty-state">
            <p>No shows yet.</p>
            <p className="muted">Run the seed script, or create one from /docs.</p>
          </div>
        )}

        {shows !== null && shows.length > 0 && (
          <div className="show-grid">
            {shows.map((show) => (
              <Link key={show.id} href={`/shows/${show.id}`} className="show-card">
                <div className="show-card-banner">
                  <span className="show-card-date">{formatDateTime(show.starts_at)}</span>
                </div>
                <div className="show-card-body">
                  <h3>{show.title}</h3>
                  <p className="muted">
                    {show.venue.name}
                    {show.venue.city ? ` · ${show.venue.city}` : ""}
                  </p>
                </div>
                <div className="show-card-footer">
                  <span className="btn btn-primary btn-sm">View seats</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
