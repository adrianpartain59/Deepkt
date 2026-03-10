"use client";

import React, { useEffect, useState, useRef, useMemo, useCallback } from "react";
import { Stage, Layer, Circle, Group, Line, Text } from "react-konva";
import { FaSoundcloud, FaSpotify, FaApple, FaYoutube, FaChevronLeft, FaChevronRight, FaPause, FaPlay, FaHeart, FaChevronDown, FaBars } from "react-icons/fa";

type PlatformKey = "soundcloud" | "spotify" | "apple_music" | "youtube_music";

const PLATFORMS: Record<PlatformKey, {
    label: string;
    icon: React.ComponentType<{ size?: number }>;
    color: string;
    buildUrl: (track: { artist: string; title: string; url?: string }) => string;
}> = {
    soundcloud: {
        label: "SoundCloud",
        icon: FaSoundcloud,
        color: "#ff5500",
        buildUrl: (t) => t.url || `https://soundcloud.com/search?q=${encodeURIComponent(t.artist + " " + t.title)}`,
    },
    spotify: {
        label: "Spotify",
        icon: FaSpotify,
        color: "#1DB954",
        buildUrl: (t) => `https://open.spotify.com/search/${encodeURIComponent(t.artist + " " + t.title)}`,
    },
    apple_music: {
        label: "Apple Music",
        icon: FaApple,
        color: "#FA243C",
        buildUrl: (t) => `https://music.apple.com/us/search?term=${encodeURIComponent(t.artist + " " + t.title)}`,
    },
    youtube_music: {
        label: "YouTube Music",
        icon: FaYoutube,
        color: "#FF0000",
        buildUrl: (t) => `https://music.youtube.com/search?q=${encodeURIComponent(t.artist + " " + t.title)}`,
    },
};

const PLATFORM_KEYS: PlatformKey[] = ["soundcloud", "spotify", "apple_music", "youtube_music"];

interface UniverseNode {
    id: string;
    artist: string;
    title: string;
    x: number;
    y: number;
    url?: string;
}

interface TagZone {
    tag: string;
    x: number;
    y: number;
    count: number;
}

const DEFAULT_ZOOM = 5.0;
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function UniverseCanvas({ onMenuOpen, activeTab }: { onMenuOpen?: () => void; activeTab?: string }) {
    const [nodes, setNodes] = useState<UniverseNode[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    // scale for rendering-dependent values like edgeOpacity (synced lazily)
    const [scaleForRender, setScaleForRender] = useState(DEFAULT_ZOOM);
    const [focalTrack, setFocalTrack] = useState<UniverseNode | null>(null);
    const [displayTrack, setDisplayTrack] = useState<UniverseNode | null>(null);
    const trackHistoryRef = useRef<UniverseNode[]>([]);
    const historyIndexRef = useRef(-1);
    const isNavigatingBackRef = useRef(false);

    // Tag Zones
    const [tagZones, setTagZones] = useState<TagZone[]>([]);

    // Entry gate — requires one click to satisfy browser autoplay policy
    // Persisted in sessionStorage so Spotify OAuth redirect doesn't reset it
    const [hasEntered, setHasEntered] = useState(() => {
        if (typeof window !== "undefined") {
            return sessionStorage.getItem("hasEntered") === "true";
        }
        return false;
    });
    const [showHint, setShowHint] = useState(false);

    // Search State
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string }[]>([]);
    const [isSearching, setIsSearching] = useState(false);

    // Sidebar State
    const [neighbors, setNeighbors] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string, match_pct?: number }[]>([]);
    const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
        if (typeof window === "undefined") return true;
        return window.innerWidth > 768;
    });

    // Liked Tracks (persisted to localStorage, ordered most-recent-first)
    const [likedTrackIds, setLikedTrackIds] = useState<string[]>(() => {
        if (typeof window === 'undefined') return [];
        try {
            const stored = localStorage.getItem('ambis-liked-tracks');
            return stored ? JSON.parse(stored) : [];
        } catch { return []; }
    });
    const likedSet = useMemo(() => new Set(likedTrackIds), [likedTrackIds]);
    const toggleLike = useCallback((trackId: string) => {
        setLikedTrackIds(prev => {
            const next = prev.includes(trackId)
                ? prev.filter(id => id !== trackId)
                : [trackId, ...prev.filter(id => id !== trackId)];
            localStorage.setItem('ambis-liked-tracks', JSON.stringify(next));
            return next;
        });
    }, []);

    // Sidebar tab: 'similar' | 'liked'
    const [sidebarTab, setSidebarTab] = useState<'similar' | 'liked'>('similar');

    // Platform switcher
    const [platform, setPlatform] = useState<PlatformKey>(() => {
        if (typeof window === 'undefined') return 'soundcloud';
        return (localStorage.getItem('preferred_platform') as PlatformKey) || 'soundcloud';
    });
    const [platformOpen, setPlatformOpen] = useState(false);
    useEffect(() => { localStorage.setItem('preferred_platform', platform); }, [platform]);
    const platformDropdownRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!platformOpen) return;
        const handleClickOutside = (e: MouseEvent) => {
            if (platformDropdownRef.current && !platformDropdownRef.current.contains(e.target as Node)) {
                setPlatformOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [platformOpen]);

    // Track history for back button (synchronous ref update during render)
    const history = trackHistoryRef.current;
    const currentHistoryTrack = historyIndexRef.current >= 0 ? history[historyIndexRef.current] : null;
    if (focalTrack && focalTrack.id !== currentHistoryTrack?.id) {
        if (isNavigatingBackRef.current) {
            isNavigatingBackRef.current = false;
        } else {
            // Trim any forward history and push new track
            trackHistoryRef.current = history.slice(0, historyIndexRef.current + 1);
            trackHistoryRef.current.push(focalTrack);
            historyIndexRef.current = trackHistoryRef.current.length - 1;
        }
    }

    // Audio Player State
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [audioState, setAudioState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
    const [autoplayBlocked, setAutoplayBlocked] = useState(false);
    const lastPlayedTrackRef = useRef<string | null>(null);

    // Web Audio analysis refs (for beat-reactive star)
    const audioContextRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const audioSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
    const audioDataRef = useRef<Uint8Array<ArrayBuffer>>(new Uint8Array(0));
    const focalGroupRef = useRef<any>(null);

    // Pause audio when navigating away from explore tab
    useEffect(() => {
        if (activeTab && activeTab !== "explore") {
            audioRef.current?.pause();
        }
    }, [activeTab]);

    // Oscilloscope
    const scopeCanvasRef = useRef<HTMLCanvasElement | null>(null);
    const scopeRafRef = useRef<number>(0);

    // Refs for imperative high-speed math without triggering React renders
    const nodesRef = useRef<UniverseNode[]>([]);
    const viewRef = useRef({ x: 0, y: 0, scale: DEFAULT_ZOOM });
    const rafRef = useRef<number>(0);
    const isDraggingRef = useRef(false);
    const zoomCooldownRef = useRef(Infinity);
    const prevViewRef = useRef({ x: 0, y: 0, scale: DEFAULT_ZOOM });
    const scaleRenderTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isInteractingRef = useRef(false);
    const interactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [isInteracting, setIsInteracting] = useState(false);
    const [visibleNodes, setVisibleNodes] = useState<UniverseNode[]>([]);
    const scopeDataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);

    // 1. Fetch Universe from FastAPI
    useEffect(() => {
        let isMounted = true;
        fetch(`${API_BASE}/api/universe`)
            .then((res) => {
                if (!res.ok) throw new Error("Failed to fetch universe");
                return res.json();
            })
            .then((data) => {
                if (!isMounted) return;
                // The UMAP math floats are usually [-5.0 to 10.0].
                // We scales them up to spread them across the virtual map.
                // We're using * 500 (reduced from 2000) so the Supervised UMAP clusters remain distinct but sit closer together.
                const scaled = data.map((n: any) => ({
                    ...n,
                    x: n.x * 500,
                    y: n.y * 500,
                }));
                setNodes(scaled);
                nodesRef.current = scaled;
                setVisibleNodes(scaled);
                // Auto-center camera on a random node so each visit starts somewhere different
                if (scaled.length > 0) {
                    const first = scaled[Math.floor(Math.random() * scaled.length)];
                    const cx = window.innerWidth / 2;
                    const cy = window.innerHeight / 2;

                    // Use the 5.0 zoom level we now default to
                    const startX = cx - first.x * DEFAULT_ZOOM;
                    const startY = cy - first.y * DEFAULT_ZOOM;

                    viewRef.current = { x: startX, y: startY, scale: DEFAULT_ZOOM };
                    // zoomCooldownRef starts at Infinity — proximity engine stays paused
                    // until the user's first interaction (scroll, drag, click, etc.)
                    setFocalTrack(first); // Make the random node the focal track on load
                    setDisplayTrack(first); // Sync display track so similar tracks panel & audio work immediately
                }
            })
            .catch((err) => console.error("API Error: ", err));

        return () => { isMounted = false; };
    }, []);

    // 1b. Fetch Tag Zones from FastAPI
    useEffect(() => {
        fetch(`${API_BASE}/api/tag-zones`)
            .then((res) => res.json())
            .then((data) => {
                const scaled = data.map((z: any) => ({
                    ...z,
                    x: z.x * 500,
                    y: z.y * 500,
                }));
                setTagZones(scaled);
            })
            .catch((err) => console.error("Tag zones fetch error:", err));
    }, []);

    useEffect(() => {
        if (hasEntered) setShowHint(true);
    }, [hasEntered]);

    // 2. Responsive Canvas Sizing
    useEffect(() => {
        const handleResize = () => {
            setDimensions({
                width: window.innerWidth,
                height: window.innerHeight,
            });
        };
        handleResize();
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    // Initialise the Web Audio graph from a user gesture so AudioContext is 'running', not 'suspended'.
    // Safe to call repeatedly — guarded by audioSourceRef.
    const initAudioGraph = () => {
        if (audioSourceRef.current || !audioRef.current) {
            audioContextRef.current?.resume();
            return;
        }
        try {
            const ctx = new AudioContext();
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 256;
            audioDataRef.current = new Uint8Array(analyser.frequencyBinCount);
            const source = ctx.createMediaElementSource(audioRef.current);
            source.connect(analyser);
            analyser.connect(ctx.destination);
            audioContextRef.current = ctx;
            analyserRef.current = analyser;
            audioSourceRef.current = source;
        } catch (e) {
            console.error('Audio graph init failed:', e);
        }
    };

    // 3. Zoom Logic (Mouse Wheel) — zooms from screen center to keep focal track pinned
    const handleWheel = (e: any) => {
        e.evt.preventDefault();
        initAudioGraph();
        const v = viewRef.current;
        const stage = stageRef.current;

        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        const centerPointTo = {
            x: (cx - v.x) / v.scale,
            y: (cy - v.y) / v.scale,
        };

        const scaleBy = 1.15;
        const newScale = e.evt.deltaY < 0 ? v.scale * scaleBy : v.scale / scaleBy;
        const clampedScale = Math.min(Math.max(newScale, 0.001), 20.0);

        viewRef.current = {
            scale: clampedScale,
            x: cx - centerPointTo.x * clampedScale,
            y: cy - centerPointTo.y * clampedScale,
        };

        if (stage) {
            stage.x(viewRef.current.x);
            stage.y(viewRef.current.y);
            stage.scaleX(clampedScale);
            stage.scaleY(clampedScale);
            stage.batchDraw();
            prevViewRef.current = { ...viewRef.current };
        }

        zoomCooldownRef.current = performance.now() + 1000;

        isInteractingRef.current = true;
        if (!isInteracting) setIsInteracting(true);
        if (interactionTimerRef.current) clearTimeout(interactionTimerRef.current);
        interactionTimerRef.current = setTimeout(() => {
            isInteractingRef.current = false;
            setIsInteracting(false);
        }, 300);

        if (scaleRenderTimerRef.current) clearTimeout(scaleRenderTimerRef.current);
        scaleRenderTimerRef.current = setTimeout(() => {
            setScaleForRender(viewRef.current.scale);
        }, 150);
    };

    const stageRef = useRef<any>(null);
    const prevFocalIdRef = useRef<string | null>(null);

    // 4. Center-Proximity Bounding Box (60fps Engine)
    useEffect(() => {
        if (dimensions.width === 0 || nodes.length === 0) return;

        let lastVisibleUpdate = 0;
        let lastCullView = { x: NaN, y: NaN, scale: NaN };

        const computeVisibleNodes = () => {
            const v = viewRef.current;

            // Skip if viewport hasn't moved since the last cull
            const dx = Math.abs(v.x - lastCullView.x);
            const dy = Math.abs(v.y - lastCullView.y);
            const ds = Math.abs(v.scale - lastCullView.scale);
            if (dx < 1 && dy < 1 && ds < 0.01) return;
            lastCullView = { x: v.x, y: v.y, scale: v.scale };

            const vw = dimensions.width / v.scale;
            const vh = dimensions.height / v.scale;
            const logCx = (dimensions.width / 2 - v.x) / v.scale;
            const logCy = (dimensions.height / 2 - v.y) / v.scale;
            const buffer = 150;

            const filtered = nodesRef.current.filter(n =>
                n.x > logCx - vw / 2 - buffer && n.x < logCx + vw / 2 + buffer &&
                n.y > logCy - vh / 2 - buffer && n.y < logCy + vh / 2 + buffer
            );
            setVisibleNodes(filtered);
        };

        const updateFocalTrack = () => {
            const now = performance.now();
            const v = viewRef.current;
            const stage = stageRef.current;
            const prevView = prevViewRef.current;

            // During interaction, skip all expensive proximity/gravity work.
            // Only sync stage position (for drag visuals) and beat-reactive star.
            if (isInteractingRef.current) {
                if (stage && (v.x !== prevView.x || v.y !== prevView.y || v.scale !== prevView.scale)) {
                    stage.x(v.x);
                    stage.y(v.y);
                    stage.scaleX(v.scale);
                    stage.scaleY(v.scale);
                    stage.batchDraw();
                    prevViewRef.current = { x: v.x, y: v.y, scale: v.scale };
                }

                if (analyserRef.current && focalGroupRef.current) {
                    analyserRef.current.getByteFrequencyData(audioDataRef.current);
                    const bassEnd = 4;
                    let sum = 0;
                    for (let i = 0; i < bassEnd; i++) sum += audioDataRef.current[i];
                    let bassAvg = (sum / bassEnd) / 255;
                    bassAvg = Math.pow(bassAvg, 3.0);
                    const focalZoom = Math.max(1.0, Math.sqrt(8.0 / v.scale));
                    const targetScale = (0.2 + (bassAvg * 3.0)) * focalZoom;
                    const currentScale = focalGroupRef.current.scaleX() || 1;
                    const lerp = targetScale > currentScale ? 0.9 : 0.08;
                    const smoothed = currentScale + (targetScale - currentScale) * lerp;
                    if (Math.abs(smoothed - currentScale) > 0.005) {
                        focalGroupRef.current.scale({ x: smoothed, y: smoothed });
                        focalGroupRef.current.getLayer()?.batchDraw();
                    }
                }

                rafRef.current = requestAnimationFrame(updateFocalTrack);
                return;
            }

            // Throttled viewport culling (only when idle)
            if (now - lastVisibleUpdate > 300) {
                lastVisibleUpdate = now;
                computeVisibleNodes();
            }

            const centerX = dimensions.width / 2;
            const centerY = dimensions.height / 2;

            const logicalCenterX = (centerX - v.x) / v.scale;
            const logicalCenterY = (centerY - v.y) / v.scale;

            const vWidth = dimensions.width / v.scale;
            const vHeight = dimensions.height / v.scale;
            const minX = logicalCenterX - (vWidth / 2) - 50;
            const maxX = logicalCenterX + (vWidth / 2) + 50;
            const minY = logicalCenterY - (vHeight / 2) - 50;
            const maxY = logicalCenterY + (vHeight / 2) + 50;

            let closestNode: UniverseNode | null = null;
            let minDistance = Infinity;

            for (let i = 0; i < nodesRef.current.length; i++) {
                const node = nodesRef.current[i];
                if (node.x < minX || node.x > maxX || node.y < minY || node.y > maxY) continue;

                const dx = node.x - logicalCenterX;
                const dy = node.y - logicalCenterY;
                const distSq = dx * dx + dy * dy;

                if (distSq < minDistance) {
                    minDistance = distSq;
                    closestNode = node;
                }
            }

            const zoomPaused = now < zoomCooldownRef.current;

            const nearestNode = closestNode;
            if (!zoomPaused) {
                setDisplayTrack((prev) => {
                    if (prev?.id !== nearestNode?.id) return nearestNode;
                    return prev;
                });
            }

            const maxLogicalRadius = 30 / v.scale;
            const maxDistanceSq = maxLogicalRadius * maxLogicalRadius;

            if (minDistance > maxDistanceSq) {
                closestNode = null;
            }

            let viewDirty = false;
            if (nearestNode && !isDraggingRef.current && !zoomPaused) {
                const targetX = centerX - nearestNode.x * v.scale;
                const targetY = centerY - nearestNode.y * v.scale;
                const dx = targetX - v.x;
                const dy = targetY - v.y;
                const distPx = Math.sqrt(dx * dx + dy * dy);

                if (distPx > 0.5) {
                    if (distPx < 2) {
                        // Snap to target to avoid infinite floating-point drift
                        viewRef.current.x = targetX;
                        viewRef.current.y = targetY;
                    } else {
                        const strength = 0.5;
                        viewRef.current.x += dx * strength;
                        viewRef.current.y += dy * strength;
                    }
                    viewDirty = true;
                }
            }

            if (stage && (viewDirty || v.x !== prevView.x || v.y !== prevView.y || v.scale !== prevView.scale)) {
                stage.x(v.x);
                stage.y(v.y);
                stage.scaleX(v.scale);
                stage.scaleY(v.scale);
                stage.batchDraw();
                prevViewRef.current = { x: v.x, y: v.y, scale: v.scale };
            }

            if (!zoomPaused) {
                setFocalTrack((prev) => {
                    if (prev?.id !== closestNode?.id) return closestNode;
                    return prev;
                });
            }

            if (analyserRef.current && focalGroupRef.current) {
                analyserRef.current.getByteFrequencyData(audioDataRef.current);
                const bassEnd = 4;
                let sum = 0;
                for (let i = 0; i < bassEnd; i++) sum += audioDataRef.current[i];
                let bassAvg = (sum / bassEnd) / 255;
                bassAvg = Math.pow(bassAvg, 3.0);
                const focalZoom = Math.max(1.0, Math.sqrt(8.0 / v.scale));
                const targetScale = (0.2 + (bassAvg * 3.0)) * focalZoom;
                const currentScale = focalGroupRef.current.scaleX() || 1;
                const lerp = targetScale > currentScale ? 0.9 : 0.08;
                const smoothed = currentScale + (targetScale - currentScale) * lerp;
                if (Math.abs(smoothed - currentScale) > 0.005) {
                    focalGroupRef.current.scale({ x: smoothed, y: smoothed });
                    focalGroupRef.current.getLayer()?.batchDraw();
                }
            }

            rafRef.current = requestAnimationFrame(updateFocalTrack);
        };

        rafRef.current = requestAnimationFrame(updateFocalTrack);
        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
    }, [dimensions, nodes.length]);

    // 5. Fetch Nearest Neighbors (debounced, skipped during interaction)
    useEffect(() => {
        if (!displayTrack) {
            setNeighbors([]);
            return;
        }
        if (isInteractingRef.current) return;

        const controller = new AbortController();
        const timer = setTimeout(() => {
            fetch(`${API_BASE}/api/neighbors/${encodeURIComponent(displayTrack.id)}`, { signal: controller.signal })
                .then(res => {
                    if (!res.ok) throw new Error("Failed to fetch neighbors");
                    return res.json();
                })
                .then(data => setNeighbors(data))
                .catch(() => {});
        }, 400);

        return () => { clearTimeout(timer); controller.abort(); };
    }, [displayTrack?.id, isInteracting]);

    // 6. Audio Player — load and play 30s snippet when focal track changes (skipped during interaction)
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio || !hasEntered) return;
        if (activeTab && activeTab !== "explore") return;
        if (isInteractingRef.current) return;

        if (!focalTrack) {
            audio.pause();
            setAudioState('idle');
            lastPlayedTrackRef.current = null;
            return;
        }

        if (lastPlayedTrackRef.current === focalTrack.id) return;
        lastPlayedTrackRef.current = focalTrack.id;

        initAudioGraph();
        setAudioState('loading');
        audio.pause();
        audio.src = `${API_BASE}/api/audio/${encodeURIComponent(focalTrack.id)}`;
        audio.load();
        audio.play()
            .then(() => setAutoplayBlocked(false))
            .catch((err) => {
                if (err.name === 'NotAllowedError') {
                    setAutoplayBlocked(true);
                    setAudioState('idle');
                }
            });
    }, [focalTrack?.id, hasEntered, isInteracting, activeTab]);

    // Spacebar toggles play/pause globally (skip when typing in an input)
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.code !== 'Space') return;
            const tag = (e.target as HTMLElement)?.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;
            e.preventDefault();
            const audio = audioRef.current;
            if (!audio) return;
            if (audioState === 'playing') {
                audio.pause();
            } else {
                audio.play().catch(() => {});
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [audioState]);

    // 7. Oscilloscope waveform drawing loop — only runs when audio is playing, throttled to 30fps
    useEffect(() => {
        if (audioState !== 'playing') {
            const canvas = scopeCanvasRef.current;
            if (canvas) {
                const ctx = canvas.getContext('2d');
                if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
            return;
        }

        const canvas = scopeCanvasRef.current;
        const analyser = analyserRef.current;
        if (!canvas || !analyser) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        if (!scopeDataRef.current) {
            scopeDataRef.current = new Uint8Array(analyser.frequencyBinCount);
        }
        const dataArray = scopeDataRef.current;
        const w = canvas.width;
        const h = canvas.height;
        const bufferLength = dataArray.length;
        const sliceWidth = w / bufferLength;

        let lastDraw = 0;
        const FRAME_INTERVAL = 33; // ~30fps

        const draw = (time: number) => {
            if (time - lastDraw >= FRAME_INTERVAL) {
                lastDraw = time;
                analyser.getByteTimeDomainData(dataArray);

                ctx.clearRect(0, 0, w, h);
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#00e5ff';
                ctx.beginPath();

                let x = 0;
                for (let i = 0; i < bufferLength; i++) {
                    const v = dataArray[i] / 128.0;
                    const y = (v * h) / 2;
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                    x += sliceWidth;
                }
                ctx.lineTo(w, h / 2);
                ctx.stroke();
            }

            scopeRafRef.current = requestAnimationFrame(draw);
        };

        scopeRafRef.current = requestAnimationFrame(draw);
        return () => { cancelAnimationFrame(scopeRafRef.current); };
    }, [audioState]);

    // Handle search/neighbor jump
    const jumpToNode = (node: UniverseNode) => {
        // Find the officially scaled node instance in our nodes array 
        // to guarantee we have the exact layout coordinates.
        const scaledNode = nodesRef.current.find(n => n.id === node.id);
        if (!scaledNode) return;

        setFocalTrack(scaledNode); // Make it the active node

        if (!stageRef.current || !viewRef.current) return;

        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        const targetScale = DEFAULT_ZOOM;
        const targetX = cx - scaledNode.x * targetScale;
        const targetY = cy - scaledNode.y * targetScale;

        // Smooth Camera Flight Animation
        const startX = viewRef.current.x;
        const startY = viewRef.current.y;
        const startScale = viewRef.current.scale;

        const duration = 800; // ms
        const startTime = performance.now();

        const animateFlight = (time: number) => {
            const elapsed = time - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease out cubic
            const ease = 1 - Math.pow(1 - progress, 3);

            const currentX = startX + (targetX - startX) * ease;
            const currentY = startY + (targetY - startY) * ease;
            const currentScale = startScale + (targetScale - startScale) * ease;

            viewRef.current = { scale: currentScale, x: currentX, y: currentY };
            setScaleForRender(currentScale);

            if (progress < 1) requestAnimationFrame(animateFlight);
        };
        // Pause gravity during flight
        zoomCooldownRef.current = performance.now() + duration + 500;
        requestAnimationFrame(animateFlight);
    };

    const jumpToPoint = (worldX: number, worldY: number) => {
        if (!stageRef.current) return;

        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        const targetScale = viewRef.current.scale;
        const targetX = cx - worldX * targetScale;
        const targetY = cy - worldY * targetScale;

        const startX = viewRef.current.x;
        const startY = viewRef.current.y;

        const duration = 600;
        const startTime = performance.now();

        const animateFlight = (time: number) => {
            const elapsed = time - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3);

            viewRef.current.x = startX + (targetX - startX) * ease;
            viewRef.current.y = startY + (targetY - startY) * ease;

            if (progress < 1) requestAnimationFrame(animateFlight);
        };
        zoomCooldownRef.current = performance.now() + duration + 500;
        setShowHint(false);
        requestAnimationFrame(animateFlight);
    };

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!searchQuery.trim()) {
            setSearchResults([]);
            return;
        }
        setIsSearching(true);
        // Simple client-side search since we have all metadata
        const query = searchQuery.toLowerCase();
        const results = nodesRef.current.filter(n =>
            n.artist.toLowerCase().includes(query) ||
            n.title.toLowerCase().includes(query)
        ).slice(0, 50);
        setSearchResults(results);
        setIsSearching(false);
    };

    const showBloom = scaleForRender >= 1.5;
    const nodeListening = scaleForRender >= 2.0;
    // Compensate for zoom so dots stay visible as tiny stars at any zoom level.
    // Uses a square root curve so the scale grows gently rather than linearly.
    const nodeScale = Math.max(1.0, Math.sqrt(1.5 / scaleForRender));

    const memoizedNodes = useMemo(() => visibleNodes.map((node) => {
        const liked = likedSet.has(node.id);
        const s = liked ? nodeScale * 4 : nodeScale;
        return (
            <Group
                key={node.id}
                id={'node-' + node.id}
                x={node.x}
                y={node.y}
                scaleX={s}
                scaleY={s}
                onMouseEnter={nodeListening ? (e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = 'crosshair';
                } : undefined}
                onMouseLeave={nodeListening ? (e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = 'grab';
                } : undefined}
                onClick={nodeListening ? () => jumpToNode(node) : undefined}
            >
                {showBloom && (
                    <Circle
                        radius={6}
                        fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                        fillRadialGradientStartRadius={0}
                        fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                        fillRadialGradientEndRadius={6}
                        fillRadialGradientColorStops={liked ? [
                            0, 'rgba(255, 45, 117, 0.5)',
                            0.4, 'rgba(255, 45, 117, 0.15)',
                            1, 'rgba(255, 45, 117, 0)'
                        ] : [
                            0, 'rgba(255, 255, 255, 0.35)',
                            0.4, 'rgba(255, 255, 255, 0.1)',
                            1, 'rgba(255, 255, 255, 0)'
                        ]}
                        perfectDrawEnabled={false}
                        listening={nodeListening}
                        hitFunc={nodeListening ? (context, shape) => {
                            context.beginPath();
                            context.arc(0, 0, 7, 0, Math.PI * 2, true);
                            context.closePath();
                            context.fillStrokeShape(shape);
                        } : undefined}
                    />
                )}
                <Circle
                    radius={0.8}
                    fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                    fillRadialGradientStartRadius={0}
                    fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                    fillRadialGradientEndRadius={0.8}
                    fillRadialGradientColorStops={liked ? [
                        0, '#ffffff',
                        0.4, '#ff7aa8',
                        0.7, 'rgba(255, 45, 117, 0.9)',
                        0.9, 'rgba(255, 45, 117, 0.6)',
                        1, 'rgba(255, 45, 117, 0)'
                    ] : [
                        0, '#ffffff',
                        0.4, '#ffffff',
                        0.7, 'rgba(255, 255, 255, 0.8)',
                        0.9, 'rgba(255, 255, 255, 0.5)',
                        1, 'rgba(255, 255, 255, 0)'
                    ]}
                    perfectDrawEnabled={false}
                    listening={false}
                />
            </Group>
        );
    }), [visibleNodes, showBloom, nodeListening, nodeScale, likedSet]);

    // Precompute nearest-neighbor edges using a grid spatial index (O(n*k) instead of O(n²))
    const memoizedEdges = useMemo(() => {
        if (nodes.length < 2) return null;

        const cellSize = 50;
        const grid = new Map<string, number[]>();
        for (let i = 0; i < nodes.length; i++) {
            const key = `${Math.floor(nodes[i].x / cellSize)},${Math.floor(nodes[i].y / cellSize)}`;
            if (!grid.has(key)) grid.set(key, []);
            grid.get(key)!.push(i);
        }

        const lines: { x1: number; y1: number; x2: number; y2: number }[] = [];
        for (let i = 0; i < nodes.length; i++) {
            const a = nodes[i];
            const gx = Math.floor(a.x / cellSize);
            const gy = Math.floor(a.y / cellSize);
            let best1Dist = Infinity, best2Dist = Infinity;
            let best1J = -1, best2J = -1;

            for (let dx = -1; dx <= 1; dx++) {
                for (let dy = -1; dy <= 1; dy++) {
                    const cell = grid.get(`${gx + dx},${gy + dy}`);
                    if (!cell) continue;
                    for (const j of cell) {
                        if (i === j) continue;
                        const ddx = a.x - nodes[j].x;
                        const ddy = a.y - nodes[j].y;
                        const d = ddx * ddx + ddy * ddy;
                        if (d < best1Dist) {
                            best2Dist = best1Dist; best2J = best1J;
                            best1Dist = d; best1J = j;
                        } else if (d < best2Dist) {
                            best2Dist = d; best2J = j;
                        }
                    }
                }
            }

            for (const bj of [best1J, best2J]) {
                if (bj < 0) continue;
                const b = nodes[bj];
                const mx = (a.x + b.x) / 2;
                const my = (a.y + b.y) / 2;
                const hx = (b.x - a.x) * 0.3;
                const hy = (b.y - a.y) * 0.3;
                lines.push({ x1: mx - hx, y1: my - hy, x2: mx + hx, y2: my + hy });
            }
        }
        return lines.map((l, i) => (
            <Line
                key={`edge-${i}`}
                points={[l.x1, l.y1, l.x2, l.y2]}
                stroke="rgba(255,255,255,1)"
                strokeWidth={1}
                strokeScaleEnabled={false}
                perfectDrawEnabled={false}
                listening={false}
            />
        ));
    }, [nodes]);

    // Tag zone labels — rendered at inverse scale so they stay readable at any zoom level.
    // Opacity peaks when zoomed out and fades as you zoom in close to individual stars.
    const tagLabelOpacity = Math.min(0.7, Math.max(0, 1.2 - scaleForRender * 0.2));
    const memoizedTagLabels = useMemo(() => tagZones.map((zone) => (
        <Text
            key={`tag-${zone.tag}`}
            x={zone.x}
            y={zone.y}
            text={zone.tag.toUpperCase()}
            fontSize={60}
            fontFamily="monospace"
            fontStyle="bold"
            fill="rgba(255, 255, 255, 0.9)"
            offsetX={zone.tag.length * 18}
            offsetY={30}
            perfectDrawEnabled={false}
            listening={false}
        />
    )), [tagZones]);

    // Edge opacity: peaks at default zoom, fades gently when zoomed out
    const edgeOpacity = Math.min(1, Math.max(0.15, 0.25 + (scaleForRender - DEFAULT_ZOOM) * 0.1));
    const showEdges = !isInteracting && scaleForRender >= 1;

    if (dimensions.width === 0) return null;

    // Entry gate overlay — one interaction satisfies browser autoplay policy
    if (!hasEntered) {
        return (
            <div
                className="absolute inset-0 bg-black flex items-center justify-center z-50 cursor-pointer"
                tabIndex={0}
                autoFocus
                onClick={() => { initAudioGraph(); setHasEntered(true); sessionStorage.setItem("hasEntered", "true"); }}
            >
                <div className="flex flex-col items-center gap-6">
                    <h1 className="text-7xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider" style={{ fontFamily: 'var(--font-maswen)' }}>
                        AMBIS
                    </h1>
                    <p className="text-l text-zinc-500 font-mono animate-pulse">
                        Click anywhere to enter the universe...
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div
            className="absolute inset-0 bg-black cursor-grab active:cursor-grabbing"
            onClick={() => {
                initAudioGraph();
                if (autoplayBlocked && audioRef.current) {
                    audioRef.current.play()
                        .then(() => setAutoplayBlocked(false))
                        .catch(() => { });
                }
            }}
        >

            {/* Top Left: Menu Button + AMBIS Title */}
            <div className="absolute top-6 left-6 z-10 flex items-center gap-4">
                <button
                    onClick={(e) => { e.stopPropagation(); onMenuOpen?.(); }}
                    className="text-zinc-400 hover:text-white transition-colors pointer-events-auto p-1"
                    title="Menu"
                >
                    <FaBars size={22} />
                </button>
                <div className="pointer-events-none">
                    <h1 className="text-6xl font-normal text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider title-glow" style={{ fontFamily: 'var(--font-maswen)' }}>
                        AMBIS
                    </h1>
                    <p className="text-m text-zinc-500 font-mono mt-1">
                        {nodes.length > 0 ? `${nodes.length} nodes active` : 'Initializing Map...'}
                    </p>
                </div>
            </div>

            {/* Top Center: Focal Track HUD */}
            {focalTrack && (
                <div className="absolute top-6 left-1/2 -translate-x-1/2 z-40">
                    <div className="bg-black/80 backdrop-blur-md border border-[#e040fb]/30 px-5 py-3 rounded-xl flex items-center gap-4 animate-in fade-in slide-in-from-top-4 duration-300 max-w-[30rem] shadow-[0_0_25px_rgba(224,64,251,0.2)] pointer-events-auto">
                        {historyIndexRef.current > 0 && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    const prevIndex = historyIndexRef.current - 1;
                                    const prevTrack = trackHistoryRef.current[prevIndex];
                                    if (prevTrack) {
                                        isNavigatingBackRef.current = true;
                                        historyIndexRef.current = prevIndex;
                                        jumpToNode(prevTrack);
                                    }
                                }}
                                className="shrink-0 p-1 text-zinc-500 hover:text-[#00e5ff] transition-colors"
                                title={`Back to ${trackHistoryRef.current[historyIndexRef.current - 1]?.artist} – ${trackHistoryRef.current[historyIndexRef.current - 1]?.title}`}
                            >
                                <FaChevronLeft size={18} />
                            </button>
                        )}
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                toggleLike(focalTrack.id);
                            }}
                            className={`shrink-0 p-1 transition-colors ${likedSet.has(focalTrack.id) ? 'text-[#ff2d75]' : 'text-zinc-500 hover:text-[#ff2d75]'}`}
                            title={likedSet.has(focalTrack.id) ? "Unlike" : "Like"}
                        >
                            <FaHeart size={20} />
                        </button>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                if (audioRef.current) {
                                    if (audioState === 'playing') {
                                        audioRef.current.pause();
                                    } else {
                                        audioRef.current.play()
                                            .then(() => setAutoplayBlocked(false))
                                            .catch(() => { });
                                    }
                                }
                            }}
                            className="text-zinc-500 hover:text-[#00e5ff] transition-colors shrink-0 p-1"
                            title={audioState === 'playing' ? "Pause" : "Play"}
                        >
                            {audioState === 'playing' ? <FaPause size={22} /> : <FaPlay size={22} />}
                        </button>
                        <div className="min-w-0 flex-1">
                            <p className="text-base font-bold text-white truncate">{focalTrack.title}</p>
                            <p className="text-sm text-zinc-400 truncate">{focalTrack.artist}</p>
                        </div>
                        {audioState === 'loading' ? (
                            <div className="w-[80px] h-[32px] shrink-0 flex items-center justify-center">
                                <div className="w-4 h-4 border-2 border-[#00e5ff] border-t-transparent rounded-full animate-spin" />
                            </div>
                        ) : (
                            <canvas
                                ref={scopeCanvasRef}
                                width={80}
                                height={32}
                                className="shrink-0 opacity-80"
                            />
                        )}
                        <a
                            href={PLATFORMS[platform].buildUrl(focalTrack)}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-zinc-500 transition-colors shrink-0 p-1"
                            title={`Open on ${PLATFORMS[platform].label}`}
                            onMouseEnter={(e) => (e.currentTarget.style.color = PLATFORMS[platform].color)}
                            onMouseLeave={(e) => (e.currentTarget.style.color = '')}
                        >
                            {React.createElement(PLATFORMS[platform].icon, { size: 22 })}
                        </a>
                    </div>
                </div>
            )}

            {showHint && (
                <div className="absolute top-[7.5rem] left-1/2 -translate-x-1/2 z-10 pointer-events-none">
                    <p className="text-2xl text-zinc-400 font-mono animate-pulse">
                        Click or drag to move around
                    </p>
                </div>
            )}

            {/* Top Right: Platform Switcher + Search Bar + Spotify Import */}
            <div className="absolute top-6 right-10 z-30 flex items-start gap-2">
                {/* Platform Switcher */}
                <div ref={platformDropdownRef} className="relative">
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setPlatformOpen(prev => !prev); }}
                        className="flex items-center justify-center gap-1.5 bg-black/80 backdrop-blur-md border border-white/20 rounded-full px-4 transition-all hover:border-white/40 h-[46px]"
                        title={`Listening on ${PLATFORMS[platform].label}`}
                    >
                        <span style={{ color: PLATFORMS[platform].color }}>{React.createElement(PLATFORMS[platform].icon, { size: 16 })}</span>
                        <FaChevronDown size={10} className={`text-zinc-500 transition-transform ${platformOpen ? 'rotate-180' : ''}`} />
                    </button>
                    {platformOpen && (
                        <div className="absolute top-full mt-2 left-0 w-48 bg-black/90 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                            {PLATFORM_KEYS.map((key) => {
                                const p = PLATFORMS[key];
                                const active = key === platform;
                                return (
                                    <button
                                        key={key}
                                        onClick={(e) => { e.stopPropagation(); setPlatform(key); setPlatformOpen(false); }}
                                        className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-mono transition-colors ${active ? 'bg-white/10 text-white' : 'text-zinc-400 hover:bg-white/5 hover:text-white'}`}
                                    >
                                        <span style={{ color: active ? p.color : undefined }}>
                                            {React.createElement(p.icon, { size: 18 })}
                                        </span>
                                        {p.label}
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Search Bar */}
                <div className="relative w-64">
                    <form onSubmit={handleSearch} className="relative">
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="Search artist or title..."
                            className="w-full bg-black/80 backdrop-blur-md border border-white/20 rounded-full py-3 px-5 text-sm font-mono text-white placeholder-zinc-500 focus:outline-none focus:border-[#00e5ff] focus:ring-1 focus:ring-[#00e5ff] transition-all"
                        />
                        <button
                            type="button"
                            onClick={(e) => {
                                e.stopPropagation();
                                if (nodesRef.current.length === 0) return;
                                const randomNode = nodesRef.current[Math.floor(Math.random() * nodesRef.current.length)];
                                jumpToNode(randomNode);
                                setSearchResults([]);
                                setSearchQuery("");
                            }}
                            className="absolute right-2 top-2 bottom-2 px-4 rounded-full bg-white/10 hover:bg-white/20 text-xs font-bold transition-colors"
                        >
                            RANDOM
                        </button>
                    </form>

                    {searchResults.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-2 bg-black/90 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl max-h-[70vh] overflow-y-auto">
                            {searchResults.map((result, i) => (
                                <div
                                    key={result.id + i}
                                    onClick={() => {
                                        jumpToNode(result as UniverseNode);
                                        setSearchResults([]);
                                        setSearchQuery("");
                                    }}
                                    className="p-3 border-b border-white/5 hover:bg-white/10 cursor-pointer transition-colors group"
                                >
                                    <p className="text-sm font-bold text-white group-hover:text-[#00e5ff] truncate">{result.title}</p>
                                    <p className="text-xs text-zinc-400 truncate">{result.artist}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

            </div>

            {/* Right: Local Neighborhood / Liked Songs Sidebar */}
            {(displayTrack || sidebarTab === 'liked') && (
                <div className="absolute top-[5rem] right-10 z-20 flex flex-row items-start">
                    {/* Thin full-height toggle tab on the left of the panel */}
                    <button
                        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                        className="w-5 self-stretch min-h-[3rem] flex items-center justify-center bg-black/80 backdrop-blur-xl border-l border-y border-white/20 rounded-l-xl hover:bg-white/15 transition-colors shrink-0"
                        title={isSidebarOpen ? 'Hide panel' : 'Show panel'}
                    >
                        {isSidebarOpen
                            ? <FaChevronRight size={7} className="text-white/40" />
                            : <FaChevronLeft size={7} className="text-white/40" />
                        }
                    </button>

                    {/* Drawer panel */}
                    {isSidebarOpen && (
                        <div className="w-80 bg-black/80 backdrop-blur-xl border border-white/20 rounded-r-xl overflow-hidden shadow-2xl animate-in fade-in slide-in-from-right-4 duration-300">
                            {/* Tab switcher */}
                            <div className="flex border-b border-white/10">
                                {displayTrack && (
                                    <button
                                        onClick={() => setSidebarTab('similar')}
                                        className={`flex-1 px-3 py-2 text-sm font-mono transition-colors ${sidebarTab === 'similar' ? 'bg-white/10 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                                    >
                                        Similar
                                    </button>
                                )}
                                <button
                                    onClick={() => setSidebarTab('liked')}
                                    className={`flex-1 px-3 py-2 text-sm font-mono transition-colors flex items-center justify-center gap-1.5 ${sidebarTab === 'liked' ? 'bg-white/10 text-[#ff2d75]' : 'text-zinc-500 hover:text-zinc-300'}`}
                                >
                                    <FaHeart size={12} /> Liked
                                </button>
                            </div>

                            {sidebarTab === 'similar' ? (
                                <>
                                    {/* Similar Tracks Header */}
                                    {displayTrack && (
                                        <div className="px-3 py-3 bg-gradient-to-br from-[#e040fb]/20 to-[#00e5ff]/20 border-b border-white/20 flex items-center gap-2">
                                            <div className="min-w-0 flex-1">
                                                <p className="text-lg font-bold text-white tracking-wide uppercase leading-tight">Similar Tracks</p>
                                                <p className="text-[11px] text-zinc-400 truncate leading-tight">{displayTrack.artist} - {displayTrack.title}</p>
                                            </div>
                                            <a href={PLATFORMS[platform].buildUrl(displayTrack)} target="_blank" rel="noreferrer"
                                                className="transition-colors p-1.5 bg-white/10 rounded-full shrink-0"
                                                style={{ color: PLATFORMS[platform].color }}
                                                onClick={(e) => e.stopPropagation()}
                                                onMouseEnter={(e) => (e.currentTarget.style.color = '#ffffff')}
                                                onMouseLeave={(e) => (e.currentTarget.style.color = PLATFORMS[platform].color)}
                                            >
                                                {React.createElement(PLATFORMS[platform].icon, { size: 14 })}
                                            </a>
                                        </div>
                                    )}

                                    {/* Nearest Neighbors List */}
                                    <div className="max-h-[calc(100vh-9rem)] overflow-y-auto">
                                        {neighbors.length > 0 ? (
                                            neighbors.map((n) => (
                                                <div key={n.id}
                                                    onClick={() => jumpToNode(n as UniverseNode)}
                                                    className="p-3 border-b border-white/5 hover:bg-white/10 cursor-pointer transition-colors group flex justify-between items-center gap-3">
                                                    <div className="font-mono text-[10px] text-[#00e5ff] w-10 text-right shrink-0">{n.match_pct != null ? `${n.match_pct}%` : ''}</div>
                                                    <div className="min-w-0 flex-1">
                                                        <p className="text-[13px] font-bold text-zinc-200 group-hover:text-white truncate transition-colors">{n.title}</p>
                                                        <p className="text-[11px] text-zinc-500 group-hover:text-zinc-300 truncate transition-colors">{n.artist}</p>
                                                    </div>
                                                    <a href={PLATFORMS[platform].buildUrl(n)} target="_blank" rel="noreferrer"
                                                        className="text-zinc-600 transition-colors p-1.5 shrink-0"
                                                        onClick={(e) => e.stopPropagation()}
                                                        onMouseEnter={(e) => (e.currentTarget.style.color = PLATFORMS[platform].color)}
                                                        onMouseLeave={(e) => (e.currentTarget.style.color = '')}
                                                    >
                                                        {React.createElement(PLATFORMS[platform].icon, { size: 16 })}
                                                    </a>
                                                </div>
                                            ))
                                        ) : (
                                            <div className="p-8 flex items-center justify-center">
                                                <div className="w-5 h-5 border-2 border-[#00e5ff] border-t-transparent flex-shrink-0 rounded-full animate-spin"></div>
                                            </div>
                                        )}
                                    </div>
                                </>
                            ) : (
                                <>
                                    {/* Liked Songs Header */}
                                    <div className="px-3 py-3 bg-gradient-to-br from-[#e040fb]/20 to-[#00e5ff]/20 border-b border-white/20">
                                        <p className="text-lg font-bold text-white tracking-wide uppercase leading-tight">Liked Songs</p>
                                        <p className="text-[11px] text-zinc-400 mt-0.5">{likedTrackIds.length} track{likedTrackIds.length !== 1 ? 's' : ''}</p>
                                        <div className="mt-2 flex gap-2">
                                            <button
                                                onClick={() => {
                                                    if (likedTrackIds.length === 0 || nodes.length === 0) return;
                                                    const nodeMap = new Map(nodes.map(n => [n.id, n]));
                                                    const likedNodes = likedTrackIds.map(id => nodeMap.get(id)).filter((n): n is UniverseNode => n != null);
                                                    if (likedNodes.length === 0) return;
                                                    const avgX = likedNodes.reduce((s, n) => s + n.x, 0) / likedNodes.length;
                                                    const avgY = likedNodes.reduce((s, n) => s + n.y, 0) / likedNodes.length;
                                                    const likedIdSet = new Set(likedTrackIds);
                                                    let best: UniverseNode | null = null;
                                                    let bestDistSq = Infinity;
                                                    for (const node of nodes) {
                                                        if (likedIdSet.has(node.id)) continue;
                                                        if (focalTrack && node.id === focalTrack.id) continue;
                                                        const dx = node.x - avgX;
                                                        const dy = node.y - avgY;
                                                        const d = dx * dx + dy * dy;
                                                        if (d < bestDistSq) {
                                                            bestDistSq = d;
                                                            best = node;
                                                        }
                                                    }
                                                    if (best) jumpToNode(best);
                                                }}
                                                disabled={likedTrackIds.length === 0}
                                                className="flex-1 py-2 px-3 rounded-lg bg-[#00e5ff]/20 hover:bg-[#00e5ff]/30 text-[#00e5ff] text-sm font-mono font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                            >
                                                Find matches
                                            </button>
                                            <button
                                                onClick={() => {
                                                    setLikedTrackIds([]);
                                                    localStorage.setItem('ambis-liked-tracks', JSON.stringify([]));
                                                }}
                                                disabled={likedTrackIds.length === 0}
                                                className="py-2 px-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-zinc-400 hover:text-white text-xs font-mono disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
                                            >
                                                Clear likes
                                            </button>
                                        </div>
                                    </div>

                                    {/* Liked Tracks List */}
                                    <div className="max-h-[calc(100vh-9rem)] overflow-y-auto">
                                        {(() => {
                                            const nodeMap = new Map(nodes.map(n => [n.id, n]));
                                            const likedNodes = likedTrackIds.map(id => nodeMap.get(id)).filter((n): n is UniverseNode => n != null);
                                            if (likedNodes.length === 0) {
                                                return (
                                                    <div className="p-8 text-center text-zinc-500 text-sm font-mono">
                                                        No liked songs yet. Like tracks from the map to add them here.
                                                    </div>
                                                );
                                            }
                                            return likedNodes.map((n) => (
                                                <div key={n.id}
                                                    onClick={() => jumpToNode(n)}
                                                    className="p-3 border-b border-white/5 hover:bg-white/10 cursor-pointer transition-colors group flex justify-between items-center gap-3">
                                                    <div className="min-w-0 flex-1">
                                                        <p className="text-[13px] font-bold text-zinc-200 group-hover:text-white truncate transition-colors">{n.title}</p>
                                                        <p className="text-[11px] text-zinc-500 group-hover:text-zinc-300 truncate transition-colors">{n.artist}</p>
                                                    </div>
                                                    <div className="flex items-center gap-1 shrink-0">
                                                        <button
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                toggleLike(n.id);
                                                            }}
                                                            className="text-[#ff2d75] hover:text-[#ff5a8f] transition-colors p-1.5"
                                                            title="Unlike"
                                                        >
                                                            <FaHeart size={14} />
                                                        </button>
                                                        <a href={PLATFORMS[platform].buildUrl(n)} target="_blank" rel="noreferrer"
                                                            className="text-zinc-600 transition-colors p-1.5"
                                                            onClick={(e) => e.stopPropagation()}
                                                            onMouseEnter={(e) => (e.currentTarget.style.color = PLATFORMS[platform].color)}
                                                            onMouseLeave={(e) => (e.currentTarget.style.color = '')}
                                                        >
                                                            {React.createElement(PLATFORMS[platform].icon, { size: 16 })}
                                                        </a>
                                                    </div>
                                                </div>
                                            ));
                                        })()}
                                    </div>
                                </>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Dead-Center Focal Reticle */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10">
                <svg width="78" height="78" viewBox="0 0 78 78" className="block" style={{ overflow: 'visible' }}>
                    {/* Outer segmented ring — spins clockwise */}
                    <g style={{ transformOrigin: '39px 39px', animation: 'reticle-spin-cw 6s linear infinite' }}>
                        <circle cx="39" cy="39" r="35" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5"
                            strokeDasharray="36.65 18.33" strokeLinecap="round" />
                    </g>
                    {/* Inner segmented ring — spins counter-clockwise */}
                    <g style={{ transformOrigin: '39px 39px', animation: 'reticle-spin-ccw 4s linear infinite' }}>
                        <circle cx="39" cy="39" r="19" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5"
                            strokeDasharray="19.9 9.95" strokeLinecap="round" />
                    </g>
                    {/* Center dot */}
                    <circle cx="39" cy="39" r="1.5" fill="rgba(255,255,255,0.8)" />
                </svg>
            </div>

            {/* Hidden Audio Player */}
            <audio
                ref={audioRef}
                crossOrigin="anonymous"
                loop
                onPlaying={() => setAudioState('playing')}
                onPause={() => setAudioState('idle')}
                onWaiting={() => setAudioState('loading')}
                onError={() => setAudioState('error')}
                style={{ display: 'none' }}
            />

            {/* 2D Interactive Map */}
            <Stage
                ref={stageRef}
                width={dimensions.width}
                height={dimensions.height}
                draggable
                onWheel={handleWheel}
                scaleX={DEFAULT_ZOOM}
                scaleY={DEFAULT_ZOOM}
                x={0}
                y={0}
                onDragStart={() => {
                    isDraggingRef.current = true;
                    isInteractingRef.current = true;
                    setIsInteracting(true);
                    setShowHint(false);
                }}
                onDragMove={(e) => {
                    viewRef.current.x = e.target.x();
                    viewRef.current.y = e.target.y();
                }}
                onDragEnd={(e) => {
                    isDraggingRef.current = false;
                    isInteractingRef.current = false;
                    setIsInteracting(false);
                    viewRef.current.x = e.target.x();
                    viewRef.current.y = e.target.y();
                    zoomCooldownRef.current = performance.now() + 600;
                }}
                onClick={(e) => {
                    if (isDraggingRef.current) return;
                    const stage = e.target.getStage();
                    if (!stage) return;
                    const pointer = stage.getPointerPosition();
                    if (!pointer) return;
                    const scale = viewRef.current.scale;
                    const worldX = (pointer.x - viewRef.current.x) / scale;
                    const worldY = (pointer.y - viewRef.current.y) / scale;
                    jumpToPoint(worldX, worldY);
                }}
            >
                {/* 
                  By separating the dots into a memoized Layer that NEVER re-renders based on focalTrack state, 
                  we eliminate the 11,000-component React lag entirely.
                */}
                {showEdges && (
                    <Layer listening={false} opacity={edgeOpacity}>
                        {memoizedEdges}
                    </Layer>
                )}
                {!isInteracting && tagLabelOpacity > 0.02 && (
                    <Layer listening={false} opacity={tagLabelOpacity}>
                        {memoizedTagLabels}
                    </Layer>
                )}
                <Layer listening={nodeListening}>
                    {memoizedNodes}
                </Layer>

                {/* Separate Layer exclusively for the active Supernova track to guarantee shadow rendering */}
                <Layer>
                    {focalTrack && (() => {
                        const focalLiked = likedSet.has(focalTrack.id);
                        return (
                            <Group x={focalTrack.x} y={focalTrack.y} listening={false}
                                ref={(node) => {
                                    focalGroupRef.current = node;
                                    if (node && prevFocalIdRef.current !== focalTrack.id) {
                                        prevFocalIdRef.current = focalTrack.id;
                                        const focalZoom = Math.max(1.0, Math.sqrt(8.0 / viewRef.current.scale));
                                        node.scale({ x: 0.3 * focalZoom, y: 0.3 * focalZoom });
                                        import('konva').then((Konva) => {
                                            if (!node || !node.getLayer()) return;

                                            new Konva.default.Tween({
                                                node: node,
                                                scaleX: focalZoom,
                                                scaleY: focalZoom,
                                                easing: Konva.default.Easings.ElasticEaseOut,
                                                duration: 0.6,
                                            }).play();
                                        });
                                    }
                                }}
                            >
                                {/* Bloom/Glow */}
                                <Circle
                                    radius={6}
                                    fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                                    fillRadialGradientStartRadius={1}
                                    fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                                    fillRadialGradientEndRadius={6}
                                    fillRadialGradientColorStops={focalLiked ? [
                                        0, 'rgba(255, 45, 117, 0.9)',
                                        0.4, 'rgba(255, 45, 117, 0.35)',
                                        1, 'rgba(255, 45, 117, 0)'
                                    ] : [
                                        0, 'rgba(0, 229, 255, 0.8)',
                                        0.4, 'rgba(0, 229, 255, 0.3)',
                                        1, 'rgba(0, 229, 255, 0)'
                                    ]}
                                    perfectDrawEnabled={false}
                                />
                                {/* Core */}
                                <Circle
                                    radius={1.5}
                                    fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                                    fillRadialGradientStartRadius={0}
                                    fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                                    fillRadialGradientEndRadius={1.5}
                                    fillRadialGradientColorStops={focalLiked ? [
                                        0, '#ffffff',
                                        0.4, '#ff7aa8',
                                        0.7, 'rgba(255, 45, 117, 0.9)',
                                        0.9, 'rgba(255, 45, 117, 0.8)',
                                        1, 'rgba(255, 45, 117, 0)'
                                    ] : [
                                        0, '#ffffff',
                                        0.4, '#ffffff',
                                        0.7, 'rgba(150, 240, 255, 0.9)',
                                        0.9, 'rgba(0, 229, 255, 0.8)',
                                        1, 'rgba(0, 229, 255, 0)'
                                    ]}
                                    perfectDrawEnabled={false}
                                />
                            </Group>
                        );
                    })()}
                </Layer>
            </Stage>
        </div>
    );
}
