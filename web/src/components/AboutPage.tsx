"use client";

import React from "react";
import { FaBars } from "react-icons/fa";

export default function AboutPage({ onMenuOpen }: { onMenuOpen: () => void }) {
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
                    ABOUT
                </h1>
                <p className="text-zinc-500 font-mono text-sm mb-10">
                    A vertical music discovery engine.
                </p>

                <div className="space-y-8 text-zinc-300 leading-relaxed font-sans font-light">
                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">A New Way to Discover Music</h2>
                        <p className="mb-4">
                            AMBIS is built to assist in <strong>vertical discovery</strong> within specific, highly-niche genres. Instead of relying on traditional recommendation algorithms that serve you popular tracks from broad categories, AMBIS digs deep into the internet to find hidden gems that perfectly match the unique acoustic and emotional profile of the music you already love.
                        </p>
                        <p>
                            Users can define their own custom genres by connecting their streaming services or by simply chatting with an LLM (Large Language Model). The LLM figures out your favorite artists and computes a mathematical &quot;seed centroid&quot;&mdash;a perfect average representation of your taste&mdash;to compare new songs against.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">The Hunt for Hidden Gems</h2>
                        <p className="mb-4">
                            Once your taste profile is established, AMBIS acts as an autonomous agent. It scours the internet through platforms like SoundCloud to find user-created playlists that match your genre definition. It collects the artists from every relevant playlist it can find.
                        </p>
                        <p>
                            It then downloads tracks from these newly discovered artists and violently cross-references them against your seed centroid. Only the tracks that sonically align with your core taste make it past the filters, surfacing incredible, unheard music that you would have otherwise never found.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">Under the Hood: CLAP & UMAP</h2>
                        <p className="mb-4">
                            To achieve this level of precision without relying on metadata tags or popularity metrics, AMBIS listens to the audio files using a neural network called <strong>CLAP (Contrastive Language-Audio Pretraining)</strong>. CLAP is an advanced AI model capable of understanding the raw audio waveforms of a song and converting them into high-dimensional mathematical vectors (embeddings) that represent the track&apos;s literal sound, tempo, and vibe.
                        </p>
                        <p>
                            Because these embeddings exist in hundreds of dimensions, they are impossible for humans to visualize. To solve this, AMBIS employs <strong>UMAP (Uniform Manifold Approximation and Projection)</strong>. UMAP is a dimensionality reduction algorithm that mathematically compresses those complex vectors down into a 2D map, while perfectly preserving the relational distances between them.
                        </p>
                        <p>
                            The result is the interactive universe you see on the explore page: similar songs are mapped directly next to each other, allowing you to visually navigate the sonic landscape of your genre.
                        </p>
                    </section>

                    <section className="pt-8 mt-8 border-t border-white/10 text-center">
                        <p className="text-sm text-zinc-500 font-mono tracking-wide">
                            Created by Adrian Partain
                        </p>
                    </section>
                </div>
            </div>
        </div>
    );
}
