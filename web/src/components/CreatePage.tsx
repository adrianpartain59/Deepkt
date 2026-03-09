"use client";

import React from "react";
import { FaBars } from "react-icons/fa";
import SpotifyImport from "./SpotifyImport";

export default function CreatePage({ onMenuOpen }: { onMenuOpen: () => void }) {
    return (
        <div className="absolute inset-0 bg-black z-50 overflow-y-auto">
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
                    Import your music and expand the universe.
                </p>

                {/* Spotify Import Section */}
                <div className="space-y-6">
                    <div className="bg-zinc-950 border border-white/10 rounded-2xl p-6">
                        <h2 className="text-lg font-bold text-white mb-1">Spotify Import</h2>
                        <p className="text-sm text-zinc-500 mb-5">
                            Connect your Spotify account to import artists from your playlists.
                        </p>
                        <SpotifyImport />
                    </div>
                </div>
            </div>
        </div>
    );
}
