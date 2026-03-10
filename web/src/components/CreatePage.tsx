"use client";

import React, { useEffect, useState, useCallback } from "react";
import { FaBars, FaPlus, FaFolder, FaTrash, FaTimes, FaUser } from "react-icons/fa";
import useAuthStore from "@/stores/authStore";
import { apiFetch } from "@/lib/api";

interface ArtistEntry {
    artist: string;
    sc_url: string;
    sc_username: string;
    tracks: { title: string; sc_track_url: string }[];
}

interface Project {
    name: string;
    slot: number;
    playlist_urls: (string | ArtistEntry)[];
    created_at: string;
}

interface SlotData {
    slot: number;
    project: Project | null;
}

export default function CreatePage({ onMenuOpen, onNavigateToAuth, onOpenProject }: { onMenuOpen: () => void; onNavigateToAuth: () => void; onOpenProject: (slot: number) => void }) {
    const { user } = useAuthStore();
    const [slots, setSlots] = useState<SlotData[]>([]);
    const [creating, setCreating] = useState<number | null>(null);
    const [newName, setNewName] = useState("");
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);

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

    useEffect(() => {
        if (user) {
            fetchSlots();
        }
    }, [user, fetchSlots]);

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
            const createdSlot = creating;
            setCreating(null);
            setNewName("");
            await fetchSlots();
            onOpenProject(createdSlot);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const handleDelete = async (slot: number) => {
        setError(null);
        try {
            const res = await apiFetch(`/api/projects/${slot}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Failed to delete project");
            setConfirmDelete(null);
            await fetchSlots();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
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
                                className="relative bg-zinc-950 border border-white/10 hover:border-white/20 rounded-xl transition-all"
                            >
                                <button
                                    onClick={() => onOpenProject(slot)}
                                    className="w-full flex items-center gap-3 px-4 py-4 text-left"
                                >
                                    <span className="text-xs font-mono text-zinc-600 w-6 text-center shrink-0">
                                        {slot}
                                    </span>
                                    <FaFolder size={14} className="text-zinc-500 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-mono truncate text-zinc-300">
                                            {project.name}
                                        </p>
                                        <p className="text-xs text-zinc-600 font-mono">
                                            {(() => {
                                                const artists = project.playlist_urls.filter((e): e is ArtistEntry => typeof e === "object" && "tracks" in e);
                                                const trackCount = artists.reduce((sum, a) => sum + a.tracks.length, 0);
                                                if (artists.length > 0) {
                                                    return `${artists.length} artist${artists.length !== 1 ? "s" : ""} · ${trackCount} track${trackCount !== 1 ? "s" : ""}`;
                                                }
                                                return `${project.playlist_urls.length} artist${project.playlist_urls.length !== 1 ? "s" : ""}`;
                                            })()}
                                        </p>
                                    </div>
                                    <span className="text-zinc-600 text-xs font-mono">→</span>
                                </button>

                                {/* Delete button */}
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
                            </div>
                        );
                    })}
                </div>

            </div>
        </div>
    );
}
