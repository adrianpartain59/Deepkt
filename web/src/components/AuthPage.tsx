"use client";

import React, { useState } from "react";
import { FaBars, FaTimes } from "react-icons/fa";
import { FcGoogle } from "react-icons/fc";
import useAuthStore from "@/stores/authStore";

const API_BASE = "";

export default function AuthPage({ onMenuOpen }: { onMenuOpen: () => void }) {
    const [mode, setMode] = useState<"signin" | "signup">("signin");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const { login, register: registerUser } = useAuthStore();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            if (mode === "signin") {
                await login(email, password);
            } else {
                if (password.length < 8) {
                    throw new Error("Password must be at least 8 characters");
                }
                await registerUser(email, password, displayName || undefined);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setLoading(false);
        }
    };

    const handleGoogleSignIn = () => {
        // Redirect in the same window — the API will redirect back to /auth/callback
        window.location.href = `${API_BASE}/api/auth/google/login`;
    };


    return (
        <div className="absolute inset-0 bg-black z-50 overflow-y-auto">
            <button
                onClick={onMenuOpen}
                className="absolute top-6 left-6 text-zinc-400 hover:text-white transition-colors p-1 z-10"
                title="Menu"
            >
                <FaBars size={22} />
            </button>
            <div className="max-w-md mx-auto px-6 py-20">
                <h1
                    className="text-4xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider mb-2"
                    style={{ fontFamily: "var(--font-maswen)" }}
                >
                    {mode === "signin" ? "SIGN IN" : "SIGN UP"}
                </h1>
                <p className="text-zinc-500 font-mono text-sm mb-10">
                    {mode === "signin"
                        ? "Sign in to access your projects."
                        : "Create an account to get started."}
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

                {/* Email + Password form */}
                <form onSubmit={handleSubmit} className="space-y-4 mb-8">
                    {mode === "signup" && (
                        <div>
                            <label className="block text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                                Display Name
                            </label>
                            <input
                                type="text"
                                value={displayName}
                                onChange={(e) => setDisplayName(e.target.value)}
                                placeholder="Optional"
                                className="w-full bg-zinc-950 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono text-white outline-none focus:border-[#e040fb]/50 transition-colors placeholder-zinc-600"
                            />
                        </div>
                    )}
                    <div>
                        <label className="block text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                            Email
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            className="w-full bg-zinc-950 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono text-white outline-none focus:border-[#e040fb]/50 transition-colors placeholder-zinc-600"
                            placeholder="you@example.com"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2">
                            Password
                        </label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            minLength={8}
                            className="w-full bg-zinc-950 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono text-white outline-none focus:border-[#e040fb]/50 transition-colors placeholder-zinc-600"
                            placeholder={mode === "signup" ? "Min 8 characters" : ""}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full py-3 rounded-xl font-mono text-sm font-bold transition-all bg-gradient-to-r from-[#e040fb] to-[#00e5ff] text-black hover:opacity-90 disabled:opacity-50"
                    >
                        {loading ? "..." : mode === "signin" ? "Sign In" : "Create Account"}
                    </button>
                </form>

                {/* Divider */}
                <div className="flex items-center gap-4 mb-8">
                    <div className="flex-1 border-t border-white/10" />
                    <span className="text-xs font-mono text-zinc-600">OR</span>
                    <div className="flex-1 border-t border-white/10" />
                </div>

                {/* OAuth buttons */}
                <div className="space-y-3 mb-10">
                    <button
                        onClick={handleGoogleSignIn}
                        className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-zinc-950 border border-white/10 rounded-xl hover:border-white/20 transition-all"
                    >
                        <FcGoogle size={18} />
                        <span className="text-sm font-mono text-zinc-400">Continue with Google</span>
                    </button>
                </div>

                {/* Toggle mode */}
                <p className="text-center text-sm font-mono text-zinc-500">
                    {mode === "signin" ? "Don't have an account?" : "Already have an account?"}{" "}
                    <button
                        onClick={() => {
                            setMode(mode === "signin" ? "signup" : "signin");
                            setError(null);
                        }}
                        className="text-[#e040fb] hover:text-[#e040fb]/80 transition-colors"
                    >
                        {mode === "signin" ? "Sign Up" : "Sign In"}
                    </button>
                </p>
            </div>
        </div>
    );
}
