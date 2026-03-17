"use client";

import React, { useEffect, useState, useCallback } from "react";
import { FaArrowLeft, FaSpotify, FaTimes, FaCheck, FaExternalLinkAlt, FaTrash, FaUndo } from "react-icons/fa";
import SpotifyImport from "./SpotifyImport";
import { apiFetch } from "@/lib/api";

interface ArtistEntry {
    artist: string;
    sc_url?: string;
    sc_username?: string;
    tracks: { title: string; sc_track_url?: string }[];
}

interface LlmOutput {
    status: string;
    tags: string[];
    seed_artists: string[];
    message: string | null;
    filtered_out: { artist: string; reason: string }[];
}

interface Project {
    name: string;
    slot: number;
    playlist_urls: (string | ArtistEntry)[];
    llm_output?: LlmOutput | null;
    created_at: string;
}

interface RemovedTrack {
    artist: string;
    title: string;
    sc_track_url: string;
    sc_url: string;
    sc_username: string;
}

const API_BASE = "";

export default function ProjectPage({
    projectSlot,
    onBack,
}: {
    projectSlot: number;
    onBack: () => void;
}) {
    const [project, setProject] = useState<Project | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [removedTracks, setRemovedTracks] = useState<RemovedTrack[]>([]);

    // Genre analysis state
    const [analyzeQuery, setAnalyzeQuery] = useState("");
    const [analyzing, setAnalyzing] = useState(false);
    const [llmResult, setLlmResult] = useState<LlmOutput | null>(null);

    // Spotify auth state
    const [spotifyConnected, setSpotifyConnected] = useState(false);
    const [spotifyChecked, setSpotifyChecked] = useState(false);

    const fetchProject = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/projects/${projectSlot}`);
            if (!res.ok) throw new Error("Failed to load project");
            const data = await res.json();
            const proj = data.project ?? data;
            setProject(proj);
            if (proj.llm_output) setLlmResult(proj.llm_output);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [projectSlot]);

    const checkSpotifyAuth = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/spotify/auth-check`);
            if (res.ok) {
                const data = await res.json();
                setSpotifyConnected(data.authenticated);
            }
        } catch {
            // Server down
        }
        setSpotifyChecked(true);
    }, []);

    // Listen for Spotify OAuth popup messages
    useEffect(() => {
        const handleMessage = (e: MessageEvent) => {
            if (e.data?.type !== "spotify-auth") return;
            if (e.data.status === "connected") {
                setSpotifyConnected(true);
            }
        };
        window.addEventListener("message", handleMessage);
        return () => window.removeEventListener("message", handleMessage);
    }, []);

    useEffect(() => {
        fetchProject();
        checkSpotifyAuth();
    }, [fetchProject, checkSpotifyAuth]);

    const handleSpotifySignIn = () => {
        const url = `${API_BASE}/api/spotify/login`;
        const w = 500, h = 700;
        const left = window.screenX + (window.outerWidth - w) / 2;
        const top = window.screenY + (window.outerHeight - h) / 2;
        window.open(url, "spotify-auth", `width=${w},height=${h},left=${left},top=${top}`);
    };

    const handleRemoveTrack = async (trackUrl: string, artist: string, title: string) => {
        if (!project) return;
        // Find the artist entry for this track so we can store full info for restore
        const artistEntry = project.playlist_urls.find(
            (e): e is ArtistEntry => typeof e === "object" && "tracks" in e && e.tracks.some((t) => t.sc_track_url === trackUrl)
        );
        // Build updated playlist_urls with the track removed
        const updatedUrls = project.playlist_urls.map((entry) => {
            if (typeof entry === "object" && "tracks" in entry) {
                const filtered = entry.tracks.filter((t) => t.sc_track_url !== trackUrl);
                if (filtered.length === 0) return null;
                return { ...entry, tracks: filtered };
            }
            return entry;
        }).filter((e) => e !== null);

        try {
            const res = await apiFetch(`/api/projects/${projectSlot}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ playlist_urls: updatedUrls }),
            });
            if (!res.ok) throw new Error("Failed to remove track");
            setRemovedTracks((prev) => [...prev, {
                artist,
                title,
                sc_track_url: trackUrl,
                sc_url: artistEntry?.sc_url ?? "",
                sc_username: artistEntry?.sc_username ?? "",
            }]);
            await fetchProject();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const handleRestoreTrack = async (removed: RemovedTrack, index: number) => {
        if (!project) return;
        const track = { title: removed.title, sc_track_url: removed.sc_track_url };
        // Try to find an existing artist entry to append to
        const updatedUrls = [...project.playlist_urls];
        const existingIdx = updatedUrls.findIndex(
            (e): e is ArtistEntry => typeof e === "object" && "tracks" in e && e.sc_url === removed.sc_url
        );
        if (existingIdx !== -1) {
            const entry = updatedUrls[existingIdx] as ArtistEntry;
            updatedUrls[existingIdx] = { ...entry, tracks: [...entry.tracks, track] };
        } else {
            updatedUrls.push({
                artist: removed.artist,
                sc_url: removed.sc_url,
                sc_username: removed.sc_username,
                tracks: [track],
            });
        }

        try {
            const res = await apiFetch(`/api/projects/${projectSlot}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ playlist_urls: updatedUrls }),
            });
            if (!res.ok) throw new Error("Failed to restore track");
            setRemovedTracks((prev) => prev.filter((_, i) => i !== index));
            await fetchProject();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const handleAnalyze = async (query?: string) => {
        setAnalyzing(true);
        setError(null);
        try {
            const res = await apiFetch(`/api/projects/${projectSlot}/analyze`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: query || analyzeQuery || undefined }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: "Analysis failed" }));
                throw new Error(err.detail || "Analysis failed");
            }
            const data = await res.json();
            setLlmResult(data);
            await fetchProject();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setAnalyzing(false);
        }
    };

    const handleImportComplete = useCallback(async () => {
        await fetchProject();
        // Auto-trigger analysis after import
        handleAnalyze();
    }, [fetchProject]);

    // Parse tracks from project data
    const artistEntries = project?.playlist_urls.filter(
        (e): e is ArtistEntry => typeof e === "object" && "tracks" in e
    ) ?? [];
    const allTracks = artistEntries.flatMap((a) =>
        a.tracks.map((t) => ({ artist: a.artist, title: t.title, sc_track_url: t.sc_track_url ?? "" }))
    );

    return (
        <div className="absolute inset-0 bg-black z-50 overflow-y-auto scrollbar-hide">
            {/* Back button */}
            <button
                onClick={onBack}
                className="absolute top-6 left-6 flex items-center gap-2 text-zinc-400 hover:text-white transition-colors p-1 z-10"
            >
                <FaArrowLeft size={16} />
                <span className="text-sm font-mono">Back</span>
            </button>

            <div className="max-w-2xl mx-auto px-6 py-20">
                {/* Project title */}
                <h1
                    className="text-4xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider mb-2"
                    style={{ fontFamily: "var(--font-maswen)" }}
                >
                    {project?.name ?? "Loading..."}
                </h1>
                {project && (
                    <p className="text-zinc-500 font-mono text-sm mb-10">
                        {artistEntries.length} artist{artistEntries.length !== 1 ? "s" : ""} · {allTracks.length} track{allTracks.length !== 1 ? "s" : ""}
                    </p>
                )}

                {/* Error banner */}
                {error && (
                    <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-2">
                        <p className="text-xs text-red-300 font-mono flex-1">{error}</p>
                        <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
                            <FaTimes size={12} />
                        </button>
                    </div>
                )}

                {/* Spotify connection + import */}
                {spotifyChecked && (
                    <div className="mb-8">
                        {spotifyConnected ? (
                            <div className="flex items-center gap-2 px-4 py-3 bg-[#1DB954]/10 border border-[#1DB954]/20 rounded-xl">
                                <FaSpotify size={16} className="text-[#1DB954]" />
                                <span className="text-sm font-mono text-[#1DB954] flex-1">Spotify connected</span>
                                <button
                                    onClick={async () => {
                                        try {
                                            await apiFetch("/api/spotify/logout", { method: "POST" });
                                        } catch {}
                                        setSpotifyConnected(false);
                                    }}
                                    className="text-xs font-mono text-zinc-500 hover:text-white transition-colors"
                                >
                                    Sign out
                                </button>
                            </div>
                        ) : (
                            <button
                                onClick={handleSpotifySignIn}
                                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-950 border border-white/10 rounded-xl hover:border-[#1DB954]/40 hover:shadow-[0_0_12px_rgba(29,185,84,0.15)] transition-all"
                            >
                                <FaSpotify size={16} className="text-[#1DB954]" />
                                <span className="text-sm font-mono text-zinc-400">Sign in with Spotify</span>
                            </button>
                        )}
                    </div>
                )}

                {/* Spotify Import Section */}
                <div className="mb-10">
                    <div
                        className={`bg-zinc-950 border rounded-2xl p-6 transition-all ${
                            spotifyConnected
                                ? "border-white/10"
                                : "border-white/5 opacity-40"
                        }`}
                    >
                        <h2 className="text-lg font-bold text-white mb-1">Spotify Import</h2>
                        <p className="text-sm text-zinc-500 mb-5">
                            {!spotifyConnected
                                ? "Sign in with Spotify above to import playlists."
                                : `Import artists from Spotify into "${project?.name ?? ""}".`}
                        </p>
                        {spotifyConnected ? (
                            <SpotifyImport
                                projectSlot={projectSlot}
                                onImportComplete={handleImportComplete}
                                isConnected={spotifyConnected}
                            />
                        ) : (
                            <div className="flex items-center gap-2 text-zinc-600 font-mono text-sm py-2">
                                <FaSpotify size={14} />
                                <span>Spotify not connected</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Genre Analysis */}
                <div className="mb-10">
                    <div className="bg-zinc-950 border border-white/10 rounded-2xl p-6">
                        <h2 className="text-lg font-bold text-white mb-1">Genre Analysis</h2>
                        <p className="text-sm text-zinc-500 mb-4">
                            Describe the subgenre or import a playlist above. Claude Haiku will generate tags and expand artist list to 30.
                        </p>
                        <div className="flex gap-2 mb-4">
                            <input
                                type="text"
                                value={analyzeQuery}
                                onChange={(e) => setAnalyzeQuery(e.target.value)}
                                placeholder="e.g. dark minimal techno like Surgeon, Regis, Female"
                                className="flex-1 bg-black border border-white/10 rounded-lg px-3 py-2 text-sm font-mono text-white placeholder-zinc-600 focus:outline-none focus:border-[#e040fb]/40"
                                onKeyDown={(e) => { if (e.key === "Enter" && !analyzing) handleAnalyze(); }}
                            />
                            <button
                                onClick={() => handleAnalyze()}
                                disabled={analyzing}
                                className="px-4 py-2 bg-[#e040fb]/20 border border-[#e040fb]/30 rounded-lg text-sm font-mono text-[#e040fb] hover:bg-[#e040fb]/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                            >
                                {analyzing ? "Analyzing..." : "Analyze"}
                            </button>
                        </div>
                        {llmResult && (
                            <div className="mt-4">
                                <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                                    Raw LLM Output
                                </p>
                                <pre className="bg-black border border-white/5 rounded-lg p-4 text-xs font-mono text-zinc-300 overflow-x-auto max-h-96 overflow-y-auto scrollbar-hide whitespace-pre-wrap">
                                    {JSON.stringify(llmResult, null, 2)}
                                </pre>
                            </div>
                        )}
                    </div>
                </div>

                {/* Matched Tracks */}
                {allTracks.length > 0 && (
                    <div className="mb-10">
                        <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-3">
                            Matched Tracks ({allTracks.length})
                        </p>
                        <div className="bg-zinc-950 border border-white/10 rounded-xl overflow-hidden">
                            <div className="max-h-96 overflow-y-auto scrollbar-hide divide-y divide-white/5">
                                {allTracks.map((t, i) => (
                                    <div
                                        key={i}
                                        className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors group"
                                    >
                                        <FaCheck size={8} className="text-[#1DB954] shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm text-white font-mono truncate">{t.title}</p>
                                            <p className="text-xs text-zinc-500 font-mono truncate">{t.artist}</p>
                                        </div>
                                        {t.sc_track_url && (
                                            <a
                                                href={t.sc_track_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-zinc-600 hover:text-[#00e5ff] transition-colors shrink-0"
                                                title="Open on SoundCloud"
                                            >
                                                <FaExternalLinkAlt size={10} />
                                            </a>
                                        )}
                                        <button
                                            onClick={() => handleRemoveTrack(t.sc_track_url, t.artist, t.title)}
                                            className="text-zinc-700 hover:text-red-400 transition-colors shrink-0 opacity-0 group-hover:opacity-100"
                                            title="Remove track"
                                        >
                                            <FaTrash size={10} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* Removed Tracks */}
                {removedTracks.length > 0 && (
                    <div className="mb-10">
                        <div className="flex items-center justify-between mb-3">
                            <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider">
                                Removed Tracks ({removedTracks.length})
                            </p>
                            <button
                                onClick={() => setRemovedTracks([])}
                                className="text-xs font-mono text-zinc-600 hover:text-zinc-400 transition-colors"
                            >
                                Clear
                            </button>
                        </div>
                        <div className="bg-zinc-950 border border-white/5 rounded-xl overflow-hidden">
                            <div className="max-h-48 overflow-y-auto scrollbar-hide divide-y divide-white/5">
                                {removedTracks.map((t, i) => (
                                    <div
                                        key={i}
                                        className="flex items-center gap-3 px-4 py-3 group"
                                    >
                                        <FaTimes size={8} className="text-zinc-600 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm text-zinc-500 font-mono truncate">{t.title}</p>
                                            <p className="text-xs text-zinc-600 font-mono truncate">{t.artist}</p>
                                        </div>
                                        <button
                                            onClick={() => handleRestoreTrack(t, i)}
                                            className="text-zinc-700 hover:text-[#1DB954] transition-colors shrink-0 opacity-0 group-hover:opacity-100"
                                            title="Restore track"
                                        >
                                            <FaUndo size={10} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* Empty state when no tracks */}
                {project && allTracks.length === 0 && removedTracks.length === 0 && (
                    <div className="text-center py-12">
                        <p className="text-zinc-600 font-mono text-sm">
                            No tracks imported yet. Use Spotify Import above to get started.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
