"use client";

import React from "react";
import { FaCompass, FaPlus, FaInfoCircle, FaCog, FaTimes, FaUser, FaSignOutAlt } from "react-icons/fa";
import useAuthStore from "@/stores/authStore";

export type PageTab = "explore" | "create" | "about" | "auth";

interface MenuPanelProps {
    isOpen: boolean;
    onClose: () => void;
    activeTab: PageTab;
    onNavigate: (tab: PageTab) => void;
    onSettings: () => void;
}

const NAV_ITEMS: { key: PageTab; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
    { key: "explore", label: "EXPLORE", icon: FaCompass },
    { key: "create", label: "CREATE", icon: FaPlus },
    { key: "about", label: "ABOUT", icon: FaInfoCircle },
];

export default function MenuPanel({ isOpen, onClose, activeTab, onNavigate, onSettings }: MenuPanelProps) {
    const { user, logout } = useAuthStore();

    return (
        <>
            {/* Backdrop */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/40 z-[60]"
                    onClick={onClose}
                />
            )}

            {/* Panel */}
            <div
                className={`fixed top-0 left-0 h-full w-72 bg-black border-r border-white/10 z-[70] flex flex-col transition-transform duration-300 ease-in-out ${
                    isOpen ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 pt-6 pb-4">
                    <h1
                        className="text-3xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider"
                        style={{ fontFamily: "var(--font-maswen)" }}
                    >
                        AMBIS
                    </h1>
                    <button
                        onClick={onClose}
                        className="text-zinc-500 hover:text-white transition-colors p-1"
                    >
                        <FaTimes size={18} />
                    </button>
                </div>

                {/* Divider */}
                <div className="mx-4 border-t border-white/10" />

                {/* Nav Items */}
                <nav className="flex-1 flex flex-col px-3 pt-4 gap-1">
                    {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
                        const active = activeTab === key;
                        return (
                            <button
                                key={key}
                                onClick={() => {
                                    onNavigate(key);
                                    onClose();
                                }}
                                className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-mono tracking-wider transition-all ${
                                    active
                                        ? "bg-white/10 text-white"
                                        : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                                }`}
                            >
                                <Icon size={16} />
                                {label}
                            </button>
                        );
                    })}
                </nav>

                {/* Bottom: User info + Settings */}
                <div className="px-3 pb-6">
                    <div className="border-t border-white/10 mx-1 mb-3" />

                    {user ? (
                        <div className="mb-3">
                            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/5">
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#e040fb] to-[#00e5ff] flex items-center justify-center text-black text-xs font-bold">
                                    {(user.display_name || user.email)[0].toUpperCase()}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm text-white font-mono truncate">
                                        {user.display_name || user.email.split("@")[0]}
                                    </p>
                                    <p className="text-xs text-zinc-500 font-mono truncate">{user.email}</p>
                                </div>
                            </div>
                            <button
                                onClick={async () => {
                                    await logout();
                                    onClose();
                                }}
                                className="flex items-center gap-3 px-4 py-2 mt-1 rounded-lg text-sm font-mono tracking-wider text-zinc-500 hover:bg-white/5 hover:text-red-400 transition-all w-full"
                            >
                                <FaSignOutAlt size={14} />
                                SIGN OUT
                            </button>
                        </div>
                    ) : (
                        <button
                            onClick={() => {
                                onNavigate("auth");
                                onClose();
                            }}
                            className={`flex items-center gap-3 px-4 py-3 mb-3 rounded-lg text-sm font-mono tracking-wider transition-all w-full ${
                                activeTab === "auth"
                                    ? "bg-white/10 text-white"
                                    : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                            }`}
                        >
                            <FaUser size={14} />
                            SIGN IN
                        </button>
                    )}

                    <button
                        onClick={() => {
                            onSettings();
                            onClose();
                        }}
                        className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-mono tracking-wider text-zinc-500 hover:bg-white/5 hover:text-zinc-300 transition-all w-full"
                    >
                        <FaCog size={16} />
                        SETTINGS
                    </button>
                </div>
            </div>
        </>
    );
}
