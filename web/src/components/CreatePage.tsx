"use client";

import React, { useEffect, useState, useCallback } from "react";
import { FaBars, FaPlus, FaFolder, FaFolderOpen, FaTrash, FaTimes, FaSpotify, FaUser } from "react-icons/fa";
import SpotifyImport from "./SpotifyImport";
import useAuthStore from "@/stores/authStore";
import { apiFetch } from "@/lib/api";

interface Project {
    name: string;
    slot: number;
    playlist_urls: string[];
    created_at: string;
}

interface SlotData {
    slot: number;
    project: Project | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function CreatePage({ onMenuOpen, onNavigateToAuth }: { onMenuOpen: () => void; onNavigateToAuth: () => void }) {
    const { user } = useAuthStore();
    const [slots, setSlots] = useState<SlotData[]>([]);
    const [activeSlot, setActiveSlot] = useState<number | null>(null);
    const [creating, setCreating] = useState<number | null>(null);
    const [newName, setNewName] = useState("");
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Spotify auth state lifted up — persists across project switches
    const [spotifyConnected, setSpotifyConnected] = useState(false);
    const [spotifyChecked, setSpotifyChecked] = useState(false);

    const activeProject = slots.find((s) => s.slot === activeSlot)?.project ?? null;

    const fetchSlots = useCallback(async () => {
        if (!user) return;
        try {
            const res = await apiFetch("/api/projects");
            if (!res.ok) throw new Error("Failed to load projects");
            const data: SlotData[] = await res.json();
            setSlots(data);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [user]);

    // Check if already authenticated with Spotify on mount
    const checkSpotifyAuth = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/spotify/auth-check`);
            if (res.ok) {
                const data = await res.json();
                setSpotifyConnected(data.authenticated);
            }
        } catch {
            // Server down or unreachable — leave as not connected
        }
        setSpotifyChecked(true);
    }, []);

    // Listen for Spotify OAuth popup messages at the page level
    useEffect(() => {
        const handleMessage = (e: MessageEvent) => {
            if (e.data?.type !== "spotify-auth") return;
            if (e.data.status === "connected") {
                setSpotifyConnected(true);
            }
        };
        window.addEventListener("message", handleMessage);

        // Fallback redirect handling
        const params = new URLSearchParams(window.location.search);
        const spotifyParam = params.get("spotify");
        if (spotifyParam === "connected") {
            setSpotifyConnected(true);
            window.history.replaceState({}, "", window.location.pathname);
        } else if (spotifyParam === "error") {
            window.history.replaceState({}, "", window.location.pathname);
        }

        return () => window.removeEventListener("message", handleMessage);
    }, []);

    useEffect(() => {
        if (user) {
            fetchSlots();
            checkSpotifyAuth();
        }
    }, [user, fetchSlots, checkSpotifyAuth]);

    const handleCreate = async () => {
        if (!newName.trim() || creating === null) return;
        setError(null);
        try {
            const res = await apiFetch("/api/projects", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: newName.trim(), slot: creating }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || "Failed to create project");
            }
            setCreating(null);
            setNewName("");
            setActiveSlot(creating);
            await fetchSlots();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const handleDelete = async (slot: number) => {
        setError(null);
        try {
            const res = await apiFetch(`/api/projects/${slot}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Failed to delete project");
            if (activeSlot === slot) setActiveSlot(null);
            setConfirmDelete(null);
            await fetchSlots();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const handleSpotifySignIn = () => {
        const url = `${API_BASE}/api/spotify/login`;
        const w = 500, h = 700;
        const left = window.screenX + (window.outerWidth - w) / 2;
        const top = window.screenY + (window.outerHeight - h) / 2;
        window.open(url, "spotify-auth", `width=${w},height=${h},left=${left},top=${top}`);
    };

    // Gate: require login
    if (!user) {
        return (
            <div className="absolute inset-0 bg-black z-50 overflow-y-auto scrollbar-hide">
                <button
                    onClick={onMenuOpen}
                    className="absolute top-6 left-6 text-zinc-400 hover:text-white transition-colors p-1 z-10"
                    title="Menu"
                >
                    <FaBars size={22} />
                </button>
                <div className="max-w-2xl mx-auto px-6 py-20">
                    <h1
                        className="text-4xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider mb-2"
                        style={{ fontFamily: "var(--font-maswen)" }}
                    >
                        CREATE
                    </h1>
                    <div className="mt-16 flex flex-col items-center gap-6">
                        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
                            <FaUser size={24} className="text-zinc-600" />
                        </div>
                        <p className="text-zinc-500 font-mono text-sm text-center">
                            Sign in to create and manage projects.
                        </p>
                        <button
                            onClick={onNavigateToAuth}
                            className="px-6 py-3 rounded-xl font-mono text-sm font-bold bg-gradient-to-r from-[#e040fb] to-[#00e5ff] text-black hover:opacity-90 transition-all"
                        >
                            Sign In
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="absolute inset-0 bg-black z-50 overflow-y-auto scrollbar-hide">
            <button
                onClick={onMenuOpen}
                className="absolute top-6 left-6 text-zinc-400 hover:text-white transition-colors p-1 z-10"
                title="Menu"
            >
                <FaBars size={22} />
            </button>
            <div className="max-w-2xl mx-auto px-6 py-20">
                <h1
                    className="text-4xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider mb-2"
                    style={{ fontFamily: "var(--font-maswen)" }}
                >
                    CREATE
                </h1>
                <p className="text-zinc-500 font-mono text-sm mb-10">
                    Select a project to get started, or create a new one.
                </p>

                {/* Spotify connection status */}
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

                {/* Error banner */}
                {error && (
                    <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-2">
                        <p className="text-xs text-red-300 font-mono flex-1">{error}</p>
                        <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
                            <FaTimes size={12} />
                        </button>
                    </div>
                )}

                {/* Project Slots */}
                <div className="space-y-3 mb-10">
                    <p className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-3">
                        Project Slots
                    </p>
                    {slots.map(({ slot, project }) => {
                        const isActive = activeSlot === slot;
                        const isCreating = creating === slot;

                        if (isCreating) {
                            return (
                                <div
                                    key={slot}
                                    className="bg-zinc-950 border border-[#e040fb]/40 rounded-xl p-4"
                                >
                                    <div className="flex items-center gap-3">
                                        <span className="text-xs font-mono text-zinc-600 w-6 text-center shrink-0">
                                            {slot}
                                        </span>
                                        <input
                                            type="text"
                                            value={newName}
                                            onChange={(e) => setNewName(e.target.value)}
                                            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                                            placeholder="Project name..."
                                            autoFocus
                                            className="flex-1 bg-transparent border-b border-white/20 text-white text-sm font-mono outline-none focus:border-[#e040fb]/60 py-1 placeholder-zinc-600"
                                        />
                                        <button
                                            onClick={handleCreate}
                                            disabled={!newName.trim()}
                                            className={`text-xs font-mono px-3 py-1.5 rounded-lg transition-all ${
                                                newName.trim()
                                                    ? "bg-[#e040fb]/20 text-[#e040fb] hover:bg-[#e040fb]/30"
                                                    : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                                            }`}
                                        >
                                            CREATE
                                        </button>
                                        <button
                                            onClick={() => {
                                                setCreating(null);
                                                setNewName("");
                                            }}
                                            className="text-zinc-500 hover:text-white transition-colors"
                                        >
                                            <FaTimes size={14} />
                                        </button>
                                    </div>
                                </div>
                            );
                        }

                        if (!project) {
                            return (
                                <button
                                    key={slot}
                                    onClick={() => {
                                        setCreating(slot);
                                        setNewName("");
                                    }}
                                    className="w-full flex items-center gap-3 px-4 py-4 bg-zinc-950 border border-dashed border-white/10 rounded-xl hover:border-white/20 hover:bg-zinc-900/50 transition-all group"
                                >
                                    <span className="text-xs font-mono text-zinc-600 w-6 text-center shrink-0">
                                        {slot}
                                    </span>
                                    <FaPlus size={12} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />
                                    <span className="text-sm font-mono text-zinc-600 group-hover:text-zinc-400 transition-colors">
                                        Empty Slot
                                    </span>
                                </button>
                            );
                        }

                        return (
                            <div
                                key={slot}
                                className={`relative bg-zinc-950 border rounded-xl transition-all ${
                                    isActive
                                        ? "border-[#e040fb]/50 shadow-[0_0_20px_rgba(224,64,251,0.1)]"
                                        : "border-white/10 hover:border-white/20"
                                }`}
                            >
                                <button
                                    onClick={() => setActiveSlot(isActive ? null : slot)}
                                    className="w-full flex items-center gap-3 px-4 py-4 text-left"
                                >
                                    <span className="text-xs font-mono text-zinc-600 w-6 text-center shrink-0">
                                        {slot}
                                    </span>
                                    {isActive ? (
                                        <FaFolderOpen size={14} className="text-[#e040fb] shrink-0" />
                                    ) : (
                                        <FaFolder size={14} className="text-zinc-500 shrink-0" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <p className={`text-sm font-mono truncate ${isActive ? "text-white" : "text-zinc-300"}`}>
                                            {project.name}
                                        </p>
                                        <p className="text-xs text-zinc-600 font-mono">
                                            {project.playlist_urls.length} artist{project.playlist_urls.length !== 1 ? "s" : ""}
                                        </p>
                                    </div>
                                    {isActive && (
                                        <span className="text-[10px] font-mono text-[#e040fb]/60 uppercase tracking-widest shrink-0">
                                            Active
                                        </span>
                                    )}
                                </button>

                                {/* Delete button */}
                                {isActive && (
                                    <div className="px-4 pb-3 flex justify-end">
                                        {confirmDelete === slot ? (
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-mono text-zinc-500">Delete?</span>
                                                <button
                                                    onClick={() => handleDelete(slot)}
                                                    className="text-xs font-mono px-2 py-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                                                >
                                                    Yes
                                                </button>
                                                <button
                                                    onClick={() => setConfirmDelete(null)}
                                                    className="text-xs font-mono px-2 py-1 rounded bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"
                                                >
                                                    No
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={() => setConfirmDelete(slot)}
                                                className="text-zinc-600 hover:text-red-400 transition-colors p-1"
                                                title="Delete project"
                                            >
                                                <FaTrash size={12} />
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Spotify Import Section - only if project is selected */}
                <div className="space-y-6">
                    <div
                        className={`bg-zinc-950 border rounded-2xl p-6 transition-all ${
                            activeProject && spotifyConnected
                                ? "border-white/10"
                                : "border-white/5 opacity-40"
                        }`}
                    >
                        <h2 className="text-lg font-bold text-white mb-1">Spotify Import</h2>
                        <p className="text-sm text-zinc-500 mb-5">
                            {!spotifyConnected
                                ? "Sign in with Spotify above to import playlists."
                                : activeProject
                                    ? `Import artists from Spotify into "${activeProject.name}".`
                                    : "Select or create a project first to import playlists."}
                        </p>
                        {activeProject && spotifyConnected ? (
                            <SpotifyImport
                                projectSlot={activeSlot!}
                                onImportComplete={fetchSlots}
                                isConnected={spotifyConnected}
                            />
                        ) : (
                            <div className="flex items-center gap-2 text-zinc-600 font-mono text-sm py-2">
                                {!spotifyConnected ? (
                                    <>
                                        <FaSpotify size={14} />
                                        <span>Spotify not connected</span>
                                    </>
                                ) : (
                                    <>
                                        <FaFolder size={14} />
                                        <span>No project selected</span>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
