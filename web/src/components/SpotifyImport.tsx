"use client";

import React, { useEffect, useState, useCallback } from "react";
import { FaSpotify, FaTimes, FaCheck, FaExclamationTriangle } from "react-icons/fa";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface Playlist {
    id: string;
    name: string;
    track_count: number;
    image_url: string | null;
}

interface ImportStatus {
    state: string;
    total: number;
    processed: number;
    matched_count: number;
    unmatched_count: number;
    matched: { artist: string; sc_url: string; sc_username: string }[];
    unmatched: { artist: string; title: string }[];
}

type Phase = "idle" | "playlists" | "importing" | "done";

export default function SpotifyImport() {
    const [isConnected, setIsConnected] = useState(false);
    const [phase, setPhase] = useState<Phase>("idle");
    const [playlists, setPlaylists] = useState<Playlist[]>([]);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [status, setStatus] = useState<ImportStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showModal, setShowModal] = useState(false);

    // Listen for postMessage from the OAuth popup
    useEffect(() => {
        const handleMessage = (e: MessageEvent) => {
            if (e.data?.type !== "spotify-auth") return;
            console.log("[SpotifyImport] received auth message:", e.data.status);
            if (e.data.status === "connected") {
                setIsConnected(true);
                setShowModal(true);
                fetchPlaylists();
            } else {
                setErrorWithLog("Spotify authentication failed. Please try again.");
            }
        };
        window.addEventListener("message", handleMessage);

        // Also handle fallback redirect (if popup was blocked)
        const params = new URLSearchParams(window.location.search);
        const spotifyParam = params.get("spotify");
        if (spotifyParam === "connected") {
            setIsConnected(true);
            setShowModal(true);
            fetchPlaylists();
            window.history.replaceState({}, "", window.location.pathname);
        } else if (spotifyParam === "error") {
            setErrorWithLog("Spotify authentication failed. Please try again.");
            window.history.replaceState({}, "", window.location.pathname);
        }

        return () => window.removeEventListener("message", handleMessage);
    }, []);

    const fetchPlaylists = useCallback(async () => {
        const url = `${API_BASE}/api/spotify/playlists`;
        try {
            const res = await fetch(url);
            if (res.status === 401) {
                setIsConnected(false);
                setPhase("idle");
                return;
            }
            if (!res.ok) {
                const body = await res.text();
                throw new Error(`GET ${url} → ${res.status} ${res.statusText}: ${body}`);
            }
            const data: Playlist[] = await res.json();
            setPlaylists(data);
            setPhase("playlists");
        } catch (e) {
            if (e instanceof TypeError) {
                // Network-level failure (CORS, DNS, server down, etc.)
                setErrorWithLog(`Network error fetching ${url}: ${e.message}`);
            } else {
                setErrorWithLog(e instanceof Error ? e.message : String(e));
            }
        }
    }, []);

    const togglePlaylist = (id: string) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const startImport = async () => {
        if (selected.size === 0) return;
        setError(null);
        setPhase("importing");

        const url = `${API_BASE}/api/spotify/import`;
        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ playlist_ids: Array.from(selected) }),
            });
            if (!res.ok) {
                const body = await res.text();
                throw new Error(`POST ${url} → ${res.status} ${res.statusText}: ${body}`);
            }
            pollStatus();
        } catch (e) {
            if (e instanceof TypeError) {
                setErrorWithLog(`Network error posting ${url}: ${e.message}`);
            } else {
                setErrorWithLog(e instanceof Error ? e.message : String(e));
            }
            setPhase("playlists");
        }
    };

    const pollStatus = useCallback(() => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE}/api/spotify/status`);
                const data: ImportStatus = await res.json();
                setStatus(data);
                if (data.state === "done") {
                    clearInterval(interval);
                    setPhase("done");
                }
            } catch {
                clearInterval(interval);
            }
        }, 2000);
    }, []);

    const setErrorWithLog = (msg: string) => {
        console.error("[SpotifyImport]", msg);
        setError(msg);
    };

    const handleSignIn = (e: React.MouseEvent) => {
        e.stopPropagation();
        const url = `${API_BASE}/api/spotify/login`;
        console.log("[SpotifyImport] opening login popup:", url);
        const w = 500, h = 700;
        const left = window.screenX + (window.outerWidth - w) / 2;
        const top = window.screenY + (window.outerHeight - h) / 2;
        window.open(url, "spotify-auth", `width=${w},height=${h},left=${left},top=${top}`);
    };

    const progressPct = status && status.total > 0
        ? Math.round((status.processed / status.total) * 100)
        : 0;

    // Sign-in button (always visible near HUD)
    if (!showModal) {
        return (
            <button
                onClick={(e) => {
                    e.stopPropagation();
                    if (isConnected) {
                        setShowModal(true);
                        if (playlists.length === 0) fetchPlaylists();
                    } else {
                        handleSignIn(e);
                    }
                }}
                className="bg-black/80 backdrop-blur-md border border-white/20 rounded-full px-4 h-[46px] flex items-center gap-2 transition-all hover:border-[#1DB954]/60 hover:shadow-[0_0_12px_rgba(29,185,84,0.3)] pointer-events-auto"
                title="Import from Spotify"
            >
                <FaSpotify size={18} className="text-[#1DB954]" />
                <span className="text-sm font-mono text-zinc-400">
                    {isConnected ? "Import" : "Sign In"}
                </span>
            </button>
        );
    }

    // Modal overlay
    return (
        <>
            {/* Trigger button still visible behind modal */}
            <button
                onClick={(e) => e.stopPropagation()}
                className="bg-black/80 backdrop-blur-md border border-[#1DB954]/50 rounded-full px-4 h-[46px] flex items-center gap-2 pointer-events-auto"
            >
                <FaSpotify size={18} className="text-[#1DB954]" />
                <span className="text-sm font-mono text-[#1DB954]">
                    {phase === "importing" ? `${progressPct}%` : "Connected"}
                </span>
            </button>

            {/* Full-screen modal backdrop */}
            <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
                onClick={(e) => {
                    e.stopPropagation();
                    if (phase !== "importing") setShowModal(false);
                }}
            >
                <div
                    className="bg-zinc-950 border border-white/10 rounded-2xl w-full max-w-lg max-h-[80vh] flex flex-col shadow-2xl overflow-hidden"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Header */}
                    <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
                        <div className="flex items-center gap-3">
                            <FaSpotify size={24} className="text-[#1DB954]" />
                            <h2 className="text-lg font-bold text-white">
                                {phase === "playlists" && "Select Playlists"}
                                {phase === "importing" && "Importing Artists"}
                                {phase === "done" && "Import Complete"}
                            </h2>
                        </div>
                        {phase !== "importing" && (
                            <button
                                onClick={() => setShowModal(false)}
                                className="text-zinc-500 hover:text-white transition-colors"
                            >
                                <FaTimes size={18} />
                            </button>
                        )}
                    </div>

                    {/* Error banner */}
                    {error && (
                        <div className="mx-6 mt-4 px-4 py-2 bg-red-500/10 border border-red-500/30 rounded-lg flex gap-2 max-h-32 overflow-y-auto">
                            <FaExclamationTriangle className="text-red-400 shrink-0 mt-0.5" />
                            <p className="text-xs text-red-300 font-mono break-all whitespace-pre-wrap">{error}</p>
                        </div>
                    )}

                    {/* Playlist selection */}
                    {phase === "playlists" && (
                        <>
                            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
                                {playlists.map((pl) => (
                                    <button
                                        key={pl.id}
                                        onClick={() => togglePlaylist(pl.id)}
                                        className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-left ${
                                            selected.has(pl.id)
                                                ? "bg-[#1DB954]/15 border border-[#1DB954]/40"
                                                : "bg-white/5 border border-transparent hover:bg-white/10"
                                        }`}
                                    >
                                        {pl.image_url ? (
                                            <img
                                                src={pl.image_url}
                                                alt=""
                                                className="w-10 h-10 rounded-lg object-cover shrink-0"
                                            />
                                        ) : (
                                            <div className="w-10 h-10 rounded-lg bg-zinc-800 shrink-0" />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium text-white truncate">
                                                {pl.name}
                                            </p>
                                            {pl.track_count > 0 && (
                                                <p className="text-xs text-zinc-500">
                                                    {pl.track_count} tracks
                                                </p>
                                            )}
                                        </div>
                                        {selected.has(pl.id) && (
                                            <FaCheck size={14} className="text-[#1DB954] shrink-0" />
                                        )}
                                    </button>
                                ))}
                                {playlists.length === 0 && (
                                    <p className="text-center text-zinc-500 py-8 font-mono">
                                        Loading playlists...
                                    </p>
                                )}
                            </div>
                            <div className="px-6 py-4 border-t border-white/10">
                                <button
                                    onClick={startImport}
                                    disabled={selected.size === 0}
                                    className={`w-full py-3 rounded-xl font-mono text-sm font-bold transition-all ${
                                        selected.size > 0
                                            ? "bg-[#1DB954] text-black hover:bg-[#1ed760]"
                                            : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                                    }`}
                                >
                                    Import {selected.size} Playlist{selected.size !== 1 ? "s" : ""}
                                </button>
                            </div>
                        </>
                    )}

                    {/* Import progress */}
                    {phase === "importing" && status && (
                        <div className="px-6 py-8 space-y-6">
                            <div className="space-y-2">
                                <div className="flex justify-between text-sm font-mono">
                                    <span className="text-zinc-400">Searching SoundCloud...</span>
                                    <span className="text-white">{status.processed} / {status.total}</span>
                                </div>
                                <div className="w-full bg-zinc-800 rounded-full h-2 overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-[#1DB954] to-[#00e5ff] transition-all duration-500 rounded-full"
                                        style={{ width: `${progressPct}%` }}
                                    />
                                </div>
                            </div>
                            <div className="flex gap-4 justify-center font-mono text-sm">
                                <div className="text-center">
                                    <p className="text-2xl font-bold text-[#1DB954]">{status.matched_count}</p>
                                    <p className="text-zinc-500">Matched</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-2xl font-bold text-zinc-500">{status.unmatched_count}</p>
                                    <p className="text-zinc-500">Unmatched</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Done */}
                    {phase === "done" && status && (
                        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
                            <div className="flex gap-4 justify-center font-mono text-sm mb-4">
                                <div className="text-center">
                                    <p className="text-3xl font-bold text-[#1DB954]">{status.matched_count}</p>
                                    <p className="text-zinc-500">Artists Found</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-3xl font-bold text-zinc-600">{status.unmatched_count}</p>
                                    <p className="text-zinc-500">Not Found</p>
                                </div>
                            </div>

                            {status.matched.length > 0 && (
                                <div>
                                    <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                                        Matched Artists
                                    </p>
                                    <div className="space-y-1">
                                        {status.matched.map((m, i) => (
                                            <div key={i} className="flex items-center gap-2 px-3 py-2 bg-[#1DB954]/5 rounded-lg">
                                                <FaCheck size={10} className="text-[#1DB954] shrink-0" />
                                                <span className="text-sm text-white truncate">{m.artist}</span>
                                                <span className="text-xs text-zinc-600 truncate ml-auto">{m.sc_username}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {status.unmatched.length > 0 && (
                                <div>
                                    <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                                        Not Found on SoundCloud
                                    </p>
                                    <div className="space-y-1">
                                        {status.unmatched.map((u, i) => (
                                            <div key={i} className="flex items-center gap-2 px-3 py-2 bg-white/5 rounded-lg">
                                                <FaTimes size={10} className="text-zinc-600 shrink-0" />
                                                <span className="text-sm text-zinc-400 truncate">{u.artist}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <p className="text-xs text-zinc-600 text-center font-mono pt-2">
                                Saved to data/spotify_seed_artists.txt
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}
