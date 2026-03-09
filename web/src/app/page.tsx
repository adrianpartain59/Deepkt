"use client";

import React, { useState } from "react";
import dynamic from "next/dynamic";
import MenuPanel, { type PageTab } from "@/components/MenuPanel";
import CreatePage from "@/components/CreatePage";
import AboutPage from "@/components/AboutPage";
import SettingsPage from "@/components/SettingsPage";

const UniverseCanvas = dynamic(() => import("@/components/UniverseCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-screen bg-black text-[#e040fb] font-mono animate-pulse">
      IGNITING UNIVERSE...
    </div>
  ),
});

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<PageTab>("explore");
  const [showSettings, setShowSettings] = useState(false);

  return (
    <main className="w-full h-screen overflow-hidden bg-black relative">
      {/* Menu panel overlay */}
      <MenuPanel
        isOpen={menuOpen}
        onClose={() => setMenuOpen(false)}
        activeTab={showSettings ? "explore" : activeTab}
        onNavigate={(tab) => {
          setActiveTab(tab);
          setShowSettings(false);
        }}
        onSettings={() => setShowSettings(true)}
      />

      {/* Universe canvas is always mounted (preserves state) */}
      <UniverseCanvas onMenuOpen={() => setMenuOpen(true)} />

      {/* Page overlays */}
      {activeTab === "create" && <CreatePage onMenuOpen={() => setMenuOpen(true)} />}
      {activeTab === "about" && <AboutPage onMenuOpen={() => setMenuOpen(true)} />}
      {showSettings && <SettingsPage onMenuOpen={() => setMenuOpen(true)} />}
    </main>
  );
}
