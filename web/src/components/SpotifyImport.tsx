"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { FaSpotify, FaTimes, FaCheck, FaExclamationTriangle, FaStop } from "react-icons/fa";
import { apiFetch } from "@/lib/api";

interface Playlist {
    id: string;
    name: string;
    track_count: number;
    image_url: string | null;
    owned: boolean;
}

interface ImportStatus {
    state: string;
    total: number;
    processed: number;
    matched_count: number;
    unmatched_count: number;
    matched: { artist: string; sc_url: string; sc_username: string }[];
    unmatched: { artist: string; title: string }[];
    error: string;
}

type Phase = "playlists" | "importing" | "done";

interface SpotifyImportProps {
    projectSlot: number;
    onImportComplete?: () => void;
    isConnected: boolean;
}

export default function SpotifyImport({ projectSlot, onImportComplete, isConnected }: SpotifyImportProps) {
    const [phase, setPhase] = useState<Phase>("playlists");
    const [playlists, setPlaylists] = useState<Playlist[]>([]);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [status, setStatus] = useState<ImportStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState(false);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchPlaylists = useCallback(async () => {
        const path = "/api/spotify/playlists";
        try {
            const res = await apiFetch(path);
            if (res.status === 401) {
                setPhase("playlists");
                return;
            }
            if (!res.ok) {
                const body = await res.text();
                throw new Error(`GET ${path} → ${res.status} ${res.statusText}: ${body}`);
            }
            const data: Playlist[] = await res.json();
            setPlaylists(data);
            setPhase("playlists");
        } catch (e) {
            if (e instanceof TypeError) {
                setErrorWithLog(`Network error fetching ${path}: ${e.message}`);
            } else {
                setErrorWithLog(e instanceof Error ? e.message : String(e));
            }
        }
    }, []);

    useEffect(() => {
        if (isConnected && playlists.length === 0) {
            fetchPlaylists();
        }
    }, [isConnected, fetchPlaylists]);

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
        setStatus(null);

        const path = "/api/spotify/import";
        try {
            const res = await apiFetch(path, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    playlist_ids: Array.from(selected),
                    project_slot: projectSlot,
                }),
            });
            if (!res.ok) {
                const body = await res.text();
                throw new Error(`POST ${path} → ${res.status} ${res.statusText}: ${body}`);
            }
            pollStatus();
        } catch (e) {
            if (e instanceof TypeError) {
                setErrorWithLog(`Network error posting ${path}: ${e.message}`);
            } else {
                setErrorWithLog(e instanceof Error ? e.message : String(e));
            }
            setPhase("playlists");
        }
    };

    const pollStatus = useCallback(() => {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(async () => {
            try {
                const res = await apiFetch("/api/spotify/status");
                const data: ImportStatus = await res.json();
                setStatus(data);
                if (data.error) {
                    setError(data.error);
                }
                if (data.state === "done") {
                    if (pollRef.current) clearInterval(pollRef.current);
                    pollRef.current = null;
                    setPhase("done");
                    if (!data.error) onImportComplete?.();
                }
            } catch {
                if (pollRef.current) clearInterval(pollRef.current);
                pollRef.current = null;
            }
        }, 2000);
    }, [onImportComplete]);

    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    const handleAbort = async () => {
        try {
            await apiFetch("/api/spotify/abort", { method: "POST" });
        } catch { /* best effort */ }
    };

    const resetImport = () => {
        setPhase("playlists");
        setSelected(new Set());
        setStatus(null);
        setError(null);
        setExpanded(false);
    };

    const setErrorWithLog = (msg: string) => {
        console.error("[SpotifyImport]", msg);
        setError(msg);
    };

    const progressPct = status && status.total > 0
        ? Math.round((status.processed / status.total) * 100)
        : 0;

    // Playlist picker (shown when not importing)
    if (phase === "playlists") {
        return (
            <div className="space-y-3">
                {error && (
                    <div className="px-4 py-2 bg-red-500/10 border border-red-500/30 rounded-lg flex gap-2 max-h-32 overflow-y-auto">
                        <FaExclamationTriangle className="text-red-400 shrink-0 mt-0.5" />
                        <p className="text-xs text-red-300 font-mono break-all whitespace-pre-wrap">{error}</p>
                    </div>
                )}

                <div className="max-h-64 overflow-y-auto scrollbar-hide space-y-2">
                    {playlists.map((pl) => (
                        <button
                            key={pl.id}
                            onClick={() => pl.owned && togglePlaylist(pl.id)}
                            disabled={!pl.owned}
                            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-left ${
                                !pl.owned
                                    ? "bg-white/[0.02] border border-transparent opacity-40 cursor-not-allowed"
                                    : selected.has(pl.id)
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
                                <p className={`text-sm font-medium truncate ${pl.owned ? "text-white" : "text-zinc-500"}`}>
                                    {pl.name}
                                </p>
                                <p className="text-xs text-zinc-500">
                                    {pl.track_count > 0 && `${pl.track_count} tracks`}
                                    {!pl.owned && (pl.track_count > 0 ? " · " : "") + "followed"}
                                </p>
                            </div>
                            {selected.has(pl.id) && (
                                <FaCheck size={14} className="text-[#1DB954] shrink-0" />
                            )}
                        </button>
                    ))}
                    {playlists.length === 0 && (
                        <p className="text-center text-zinc-500 py-8 font-mono text-sm">
                            Loading playlists...
                        </p>
                    )}
                </div>

                {playlists.length > 0 && (
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
                )}
            </div>
        );
    }

    // Progress pill + expandable panel (importing & done)
    return (
        <div className="space-y-2">
            {/* Compact progress pill */}
            <button
                onClick={() => setExpanded(!expanded)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                    error
                        ? "bg-red-500/10 border border-red-500/30"
                        : phase === "done"
                            ? "bg-[#1DB954]/10 border border-[#1DB954]/30"
                            : "bg-white/5 border border-white/10"
                }`}
            >
                <FaSpotify size={18} className={error ? "text-red-400" : "text-[#1DB954]"} />

                {/* Progress bar (inline) */}
                <div className="flex-1 min-w-0">
                    {phase === "importing" && (
                        <div className="flex items-center gap-3">
                            <div className="flex-1 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-[#1DB954] to-[#00e5ff] transition-all duration-500 rounded-full"
                                    style={{ width: `${progressPct}%` }}
                                />
                            </div>
                            <span className="text-xs font-mono text-zinc-400 shrink-0">
                                {status && status.total > 0
                                    ? `${status.processed}/${status.total}`
                                    : "Starting..."}
                            </span>
                        </div>
                    )}
                    {phase === "done" && !error && (
                        <span className="text-sm font-mono text-[#1DB954]">
                            Complete — {status?.matched_count ?? 0} artists found
                        </span>
                    )}
                    {error && (
                        <span className="text-sm font-mono text-red-400 truncate block">
                            {error}
                        </span>
                    )}
                </div>

                {/* Abort button */}
                {phase === "importing" && (
                    <button
                        onClick={(e) => { e.stopPropagation(); handleAbort(); }}
                        className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                        title="Abort import"
                    >
                        <FaStop size={12} />
                    </button>
                )}

                {/* Dismiss button (when done) */}
                {phase === "done" && (
                    <button
                        onClick={(e) => { e.stopPropagation(); resetImport(); }}
                        className="text-zinc-500 hover:text-white transition-colors p-1"
                        title="Dismiss"
                    >
                        <FaTimes size={12} />
                    </button>
                )}
            </button>

            {/* Expandable details panel */}
            {expanded && status && (phase === "importing" || phase === "done") && (
                <div className="bg-zinc-900/80 border border-white/10 rounded-xl overflow-hidden">
                    {/* Stats row */}
                    <div className="flex gap-4 justify-center font-mono text-sm px-4 py-3 border-b border-white/5">
                        <div className="text-center">
                            <p className="text-lg font-bold text-[#1DB954]">{status.matched_count}</p>
                            <p className="text-xs text-zinc-500">Matched</p>
                        </div>
                        <div className="text-center">
                            <p className="text-lg font-bold text-zinc-500">{status.unmatched_count}</p>
                            <p className="text-xs text-zinc-500">Unmatched</p>
                        </div>
                    </div>

                    {/* Results list */}
                    <div className="max-h-48 overflow-y-auto scrollbar-hide px-4 py-2 space-y-1">
                        {status.matched.map((m, i) => (
                            <div key={`m-${i}`} className="flex items-center gap-2 px-2 py-1.5 rounded-lg">
                                <FaCheck size={8} className="text-[#1DB954] shrink-0" />
                                <span className="text-xs text-white truncate">{m.artist}</span>
                                <span className="text-xs text-zinc-600 truncate ml-auto">{m.sc_username}</span>
                            </div>
                        ))}
                        {status.unmatched.map((u, i) => (
                            <div key={`u-${i}`} className="flex items-center gap-2 px-2 py-1.5 rounded-lg">
                                <FaTimes size={8} className="text-zinc-600 shrink-0" />
                                <span className="text-xs text-zinc-500 truncate">{u.artist}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
