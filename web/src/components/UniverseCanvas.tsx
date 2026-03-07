"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { Stage, Layer, Circle, Group } from "react-konva";
import { FaSoundcloud, FaChevronDown, FaChevronRight, FaVolumeUp, FaVolumeMute } from "react-icons/fa";

interface UniverseNode {
    id: string;
    artist: string;
    title: string;
    x: number;
    y: number;
    url?: string;
}

export default function UniverseCanvas() {
    const [nodes, setNodes] = useState<UniverseNode[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const [scale, setScale] = useState(2.0); // Start zoomed much closer
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [focalTrack, setFocalTrack] = useState<UniverseNode | null>(null);

    // Search State
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string }[]>([]);
    const [isSearching, setIsSearching] = useState(false);

    // Sidebar State
    const [neighbors, setNeighbors] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string }[]>([]);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    // Audio Player State
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [audioState, setAudioState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
    const [isMuted, setIsMuted] = useState(false);
    const [autoplayBlocked, setAutoplayBlocked] = useState(false);
    const lastPlayedTrackRef = useRef<string | null>(null);

    // Web Audio analysis refs (for beat-reactive star)
    const audioContextRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const audioSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
    const audioDataRef = useRef<Uint8Array>(new Uint8Array(0));
    const focalGroupRef = useRef<any>(null);

    // Refs for imperative high-speed math without triggering React renders
    const nodesRef = useRef<UniverseNode[]>([]);
    const viewRef = useRef({ x: 0, y: 0, scale: 2.0 });
    const rafRef = useRef<number>(0);

    // 1. Fetch Universe from FastAPI
    useEffect(() => {
        let isMounted = true;
        fetch("http://127.0.0.1:8000/api/universe")
            .then((res) => {
                if (!res.ok) throw new Error("Failed to fetch universe");
                return res.json();
            })
            .then((data) => {
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
                // Auto-center camera precisely on the very first node so user doesn't spawn in empty space
                if (scaled.length > 0) {
                    const first = scaled[0];
                    const cx = window.innerWidth / 2;
                    const cy = window.innerHeight / 2;

                    // Use the 5.0 zoom level we now default to
                    const startX = cx - first.x * 2.0;
                    const startY = cy - first.y * 2.0;

                    setPosition({ x: startX, y: startY });
                    viewRef.current.x = startX;
                    viewRef.current.y = startY;
                    setFocalTrack(first); // Make the first node the focal track on load
                }
            })
            .catch((err) => console.error("API Error: ", err));

        return () => { isMounted = false; };
    }, []);

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

    // 3. Zoom Logic (Mouse Wheel)
    const handleWheel = (e: any) => {
        e.evt.preventDefault();
        initAudioGraph();
        const stage = e.target.getStage();
        const oldScale = stage.scaleX();

        const pointer = stage.getPointerPosition();
        const mousePointTo = {
            x: (pointer.x - stage.x()) / oldScale,
            y: (pointer.y - stage.y()) / oldScale,
        };

        // Zoom speed
        const scaleBy = 1.05;
        const newScale = e.evt.deltaY < 0 ? oldScale * scaleBy : oldScale / scaleBy;

        const clampedScale = Math.min(Math.max(newScale, 0.001), 20.0);

        setScale(clampedScale);
        setPosition({
            x: pointer.x - mousePointTo.x * clampedScale,
            y: pointer.y - mousePointTo.y * clampedScale,
        });

        // Update physics ref
        viewRef.current = {
            scale: clampedScale,
            x: pointer.x - mousePointTo.x * clampedScale,
            y: pointer.y - mousePointTo.y * clampedScale
        };
    };

    const stageRef = useRef<any>(null);
    const prevFocalIdRef = useRef<string | null>(null);

    // 4. Center-Proximity Bounding Box (60fps Engine)
    useEffect(() => {
        if (dimensions.width === 0 || nodes.length === 0) return;

        const updateFocalTrack = () => {
            const centerX = dimensions.width / 2;
            const centerY = dimensions.height / 2;
            const v = viewRef.current;

            // Convert Screen Center to Canvas logical coordinates
            const logicalCenterX = (centerX - v.x) / v.scale;
            const logicalCenterY = (centerY - v.y) / v.scale;

            // Spatial Filter Bounding Box: Check all dots visible inside the current screen bounds
            const vWidth = dimensions.width / v.scale;
            const vHeight = dimensions.height / v.scale;
            const minX = logicalCenterX - (vWidth / 2) - 50; // 50px rendering buffer
            const maxX = logicalCenterX + (vWidth / 2) + 50;
            const minY = logicalCenterY - (vHeight / 2) - 50;
            const maxY = logicalCenterY + (vHeight / 2) + 50;

            let closestNode: UniverseNode | null = null;
            let minDistance = Infinity;

            for (let i = 0; i < nodesRef.current.length; i++) {
                const node = nodesRef.current[i];

                // Fast bounding-box exclusion (no square roots)
                if (node.x < minX || node.x > maxX || node.y < minY || node.y > maxY) {
                    continue;
                }

                // If inside bounds, calculate true Pythagorean distance
                const dx = node.x - logicalCenterX;
                const dy = node.y - logicalCenterY;
                const distSq = dx * dx + dy * dy; // We can just compare squared distances for speed

                if (distSq < minDistance) {
                    minDistance = distSq;
                    closestNode = node;
                }
            }

            // Only allow nodes within a 30 screen-pixel radius to become the Focal Track
            // This forces the user to align the node inside the reticle, rather than implicitly playing the closest faraway node.
            const maxLogicalRadius = 30 / v.scale;
            const maxDistanceSq = maxLogicalRadius * maxLogicalRadius;

            if (minDistance > maxDistanceSq) {
                closestNode = null;
            }

            // Use React state to trigger the secondary Layer overlay
            setFocalTrack((prev) => {
                if (prev?.id !== closestNode?.id) return closestNode;
                return prev;
            });

            // Beat-reactive star: read bass amplitude and scale the focal group imperatively
            if (analyserRef.current && focalGroupRef.current) {
                analyserRef.current.getByteFrequencyData(audioDataRef.current);
                // Average the bass bins (bottom 15% of spectrum = kick/bass)
                const bassEnd = Math.floor(audioDataRef.current.length * 0.15);
                let sum = 0;
                for (let i = 0; i < bassEnd; i++) sum += audioDataRef.current[i];
                const bassAvg = sum / bassEnd / 255; // 0.0 → 1.0
                const targetScale = 1 + bassAvg;
                // Exponential smoothing for organic feel
                const currentScale = focalGroupRef.current.scaleX() ?? 1;
                const smoothed = currentScale + (targetScale - currentScale) * 0.3;
                focalGroupRef.current.scale({ x: smoothed, y: smoothed });
                focalGroupRef.current.getLayer()?.batchDraw();
            }

            rafRef.current = requestAnimationFrame(updateFocalTrack);
        };

        rafRef.current = requestAnimationFrame(updateFocalTrack);
        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
    }, [dimensions, nodes.length]);

    // 5. Fetch Nearest Neighbors when Focal Track changes
    useEffect(() => {
        if (!focalTrack) {
            setNeighbors([]);
            return;
        }

        // We only want to fetch if this is a distinctly new focal track
        let isMounted = true;
        fetch(`http://127.0.0.1:8000/api/neighbors/${encodeURIComponent(focalTrack.id)}`)
            .then(res => {
                if (!res.ok) throw new Error("Failed to fetch neighbors");
                return res.json();
            })
            .then(data => {
                if (isMounted) setNeighbors(data);
            })
            .catch(err => console.error("Neighbor fetch error:", err));

        return () => { isMounted = false; };
    }, [focalTrack?.id]);

    // 6. Audio Player — load and play 30s snippet when focal track changes
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;

        if (!focalTrack) {
            audio.pause();
            setAudioState('idle');
            lastPlayedTrackRef.current = null;
            return;
        }

        if (lastPlayedTrackRef.current === focalTrack.id) return;
        lastPlayedTrackRef.current = focalTrack.id;

        setAudioState('loading');
        audio.pause();
        audio.src = `http://127.0.0.1:8000/api/audio/${encodeURIComponent(focalTrack.id)}`;
        audio.load();
        audio.play()
            .then(() => setAutoplayBlocked(false))
            .catch((err) => {
                if (err.name === 'NotAllowedError') {
                    setAutoplayBlocked(true);
                    setAudioState('idle');
                }
            });
    }, [focalTrack?.id]);

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
        const targetScale = 12.0;
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

            setScale(currentScale);
            setPosition({ x: currentX, y: currentY });

            viewRef.current.scale = currentScale;
            viewRef.current.x = currentX;
            viewRef.current.y = currentY;

            if (progress < 1) requestAnimationFrame(animateFlight);
        };
        requestAnimationFrame(animateFlight);

        // Don't arbitrarily clear search results here, let the user decide when to close it
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
        ).slice(0, 10);
        setSearchResults(results);
        setIsSearching(false);
    };

    const memoizedNodes = useMemo(() => nodes.map((node) => (
        <Group
            key={node.id}
            id={'node-' + node.id}
            x={node.x}
            y={node.y}
            onMouseEnter={(e) => {
                const container = e.target.getStage()?.container();
                if (container) container.style.cursor = 'crosshair';
            }}
            onMouseLeave={(e) => {
                const container = e.target.getStage()?.container();
                if (container) container.style.cursor = 'grab';
            }}
            onClick={() => {
                // Konva node positions are already scaled by 2000x when we created them in the API handler
                // So we just pass x,y and let jumpToNode handle calculating the center
                const cx = window.innerWidth / 2;
                const cy = window.innerHeight / 2;
                const targetScale = 12.0;
                const targetX = cx - node.x * targetScale;
                const targetY = cy - node.y * targetScale;

                const startX = viewRef.current.x;
                const startY = viewRef.current.y;
                const startScale = viewRef.current.scale;

                const duration = 800; // ms
                const startTime = performance.now();

                const animateFlight = (time: number) => {
                    const elapsed = time - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    const ease = 1 - Math.pow(1 - progress, 3);

                    const currentX = startX + (targetX - startX) * ease;
                    const currentY = startY + (targetY - startY) * ease;
                    const currentScale = startScale + (targetScale - startScale) * ease;

                    setScale(currentScale);
                    setPosition({ x: currentX, y: currentY });

                    viewRef.current.scale = currentScale;
                    viewRef.current.x = currentX;
                    viewRef.current.y = currentY;

                    if (progress < 1) requestAnimationFrame(animateFlight);
                };
                requestAnimationFrame(animateFlight);
            }}
        >
            {/* Bloom/Glow */}
            <Circle
                radius={6}
                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                fillRadialGradientStartRadius={0}
                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                fillRadialGradientEndRadius={6}
                fillRadialGradientColorStops={[
                    0, 'rgba(255, 255, 255, 0.35)',
                    0.4, 'rgba(255, 255, 255, 0.1)',
                    1, 'rgba(255, 255, 255, 0)'
                ]}
                perfectDrawEnabled={false}
                listening={true}
                hitFunc={(context, shape) => {
                    context.beginPath();
                    context.arc(0, 0, 7, 0, Math.PI * 2, true);
                    context.closePath();
                    context.fillStrokeShape(shape);
                }}
            />
            {/* Core */}
            <Circle
                radius={0.8}
                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                fillRadialGradientStartRadius={0}
                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                fillRadialGradientEndRadius={0.8}
                fillRadialGradientColorStops={[
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
    )), [nodes]);

    if (dimensions.width === 0) return null;

    return (
        <div
            className="absolute inset-0 bg-black cursor-grab active:cursor-grabbing"
            onClick={() => {
                initAudioGraph();
                if (autoplayBlocked && audioRef.current) {
                    audioRef.current.play()
                        .then(() => setAutoplayBlocked(false))
                        .catch(() => {});
                }
            }}
        >

            {/* HUD Fixed Overlay */}
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none flex flex-col items-center">
                <h1 className="text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider title-glow">
                    AMBIS
                </h1>
                <p className="text-center text-xs text-zinc-500 font-mono mt-1 mb-8">
                    {nodes.length > 0 ? `${nodes.length} nodes active` : 'Initializing Map...'}
                </p>

                {/* Focal Track Display */}
                {focalTrack && (
                    <div className="bg-black/80 backdrop-blur-md border border-[#e040fb]/30 p-3 rounded-xl flex flex-col items-center animate-in fade-in slide-in-from-top-4 duration-300 w-[32rem] shadow-[0_0_30px_rgba(224,64,251,0.2)] pointer-events-auto">
                        <div className="flex items-center gap-2 mb-1 w-full justify-center">
                            <p className="text-[10px] text-[#00e5ff] uppercase tracking-widest font-bold">Focal Track</p>
                            {audioState === 'loading' && (
                                <div className="w-2.5 h-2.5 border border-[#00e5ff] border-t-transparent rounded-full animate-spin" />
                            )}
                            {audioState === 'playing' && !isMuted && (
                                <div className="w-2 h-2 rounded-full bg-[#00e5ff] animate-pulse" />
                            )}
                        </div>
                        <h2 className="text-xl font-bold text-white text-center w-full truncate">{focalTrack.title}</h2>
                        <h3 className="text-sm text-zinc-400 text-center w-full truncate">{focalTrack.artist}</h3>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                if (audioRef.current) {
                                    const next = !isMuted;
                                    audioRef.current.muted = next;
                                    setIsMuted(next);
                                    if (!next && autoplayBlocked) {
                                        audioRef.current.play()
                                            .then(() => setAutoplayBlocked(false))
                                            .catch(() => {});
                                    }
                                }
                            }}
                            className="mt-2 text-zinc-600 hover:text-[#00e5ff] transition-colors"
                            title={isMuted ? "Unmute" : "Mute"}
                        >
                            {isMuted ? <FaVolumeMute size={11} /> : <FaVolumeUp size={11} />}
                        </button>
                        {autoplayBlocked && (
                            <p className="text-[9px] text-zinc-600 font-mono mt-1">click to enable audio</p>
                        )}
                    </div>
                )}
            </div>

            {/* Top Right: Search Bar */}
            <div className="absolute top-6 right-6 z-30 w-80">
                <form onSubmit={handleSearch} className="relative">
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search artist or title..."
                        className="w-full bg-black/80 backdrop-blur-md border border-white/20 rounded-full py-3 px-5 text-sm font-mono text-white placeholder-zinc-500 focus:outline-none focus:border-[#00e5ff] focus:ring-1 focus:ring-[#00e5ff] transition-all"
                    />
                    <button type="submit" className="absolute right-2 top-2 bottom-2 px-4 rounded-full bg-white/10 hover:bg-white/20 text-xs font-bold transition-colors">
                        {isSearching ? '...' : 'JUMP'}
                    </button>
                </form>

                {searchResults.length > 0 && (
                    <div className="mt-2 bg-black/90 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl max-h-96 overflow-y-auto">
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

            {/* Top Right (Below Search): Local Neighborhood Sidebar */}
            <div className="absolute top-24 right-5 z-20 flex flex-col items-end">
                {/* Collapse Toggle Pill */}
                <button
                    onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                    className="mb-2 px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border border-white/20 text-xs font-bold text-white transition-all flex items-center gap-2"
                >
                    {isSidebarOpen ? (
                        <><FaChevronDown className="text-[10px]" /> Hide Neighbors</>
                    ) : (
                        <><FaChevronRight className="text-[10px]" /> Local Neighborhood</>
                    )}
                </button>

                {/* Sidebar Drawer */}
                {isSidebarOpen && focalTrack && (
                    <div className="w-80 bg-black/80 backdrop-blur-xl border border-white/20 rounded-2xl overflow-hidden shadow-2xl animate-in fade-in slide-in-from-right-8 duration-300">
                        {/* Header: The Focal Track itself */}
                        <div className="p-4 bg-gradient-to-br from-[#e040fb]/20 to-[#00e5ff]/20 border-b border-white/20">
                            <p className="text-[10px] text-[#00e5ff] uppercase tracking-widest font-bold mb-1">Local Center</p>
                            <div className="flex justify-between items-center gap-3">
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-bold text-white truncate">{focalTrack.title}</p>
                                    <p className="text-xs text-zinc-300 truncate">{focalTrack.artist}</p>
                                </div>
                                {/* Soundcloud Link */}
                                <a href={focalTrack.url || `https://soundcloud.com/search?q=${encodeURIComponent(focalTrack.artist + ' ' + focalTrack.title)}`} target="_blank" rel="noreferrer"
                                    className="text-[#ff5500] hover:text-white transition-colors p-2 bg-white/10 rounded-full shrink-0"
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    <FaSoundcloud size={18} />
                                </a>
                            </div>
                        </div>

                        {/* Nearest Neighbors List */}
                        <div className="max-h-[60vh] overflow-y-auto">
                            {neighbors.length > 0 ? (
                                neighbors.map((n, i) => (
                                    <div key={n.id}
                                        onClick={() => jumpToNode(n as UniverseNode)}
                                        className="p-3 border-b border-white/5 hover:bg-white/10 cursor-pointer transition-colors group flex justify-between items-center gap-3">
                                        <div className="font-mono text-[10px] text-zinc-500 w-4 text-right shrink-0">{i + 1}</div>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-[13px] font-bold text-zinc-200 group-hover:text-white truncate transition-colors">{n.title}</p>
                                            <p className="text-[11px] text-zinc-500 group-hover:text-zinc-300 truncate transition-colors">{n.artist}</p>
                                        </div>
                                        {n.url && (
                                            <a href={n.url} target="_blank" rel="noreferrer"
                                                className="text-zinc-600 hover:text-[#ff5500] transition-colors p-1.5 shrink-0"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <FaSoundcloud size={16} />
                                            </a>
                                        )}
                                    </div>
                                ))
                            ) : (
                                <div className="p-8 flex items-center justify-center">
                                    <div className="w-5 h-5 border-2 border-[#00e5ff] border-t-transparent flex-shrink-0 rounded-full animate-spin"></div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Dead-Center Focal Reticle */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full border border-white/20 pointer-events-none z-10 flex items-center justify-center">
                <div className="w-1 h-1 bg-white rounded-full"></div>
            </div>

            {/* Hidden Audio Player */}
            <audio
                ref={audioRef}
                crossOrigin="anonymous"
                loop
                onPlaying={() => setAudioState('playing')}
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
                scaleX={scale}
                scaleY={scale}
                x={position.x}
                y={position.y}
                onDragMove={(e) => {
                    // Update physics ref continuously while dragging
                    viewRef.current.x = e.target.x();
                    viewRef.current.y = e.target.y();
                }}
                onDragEnd={(e) => {
                    setPosition({ x: e.target.x(), y: e.target.y() });
                    viewRef.current.x = e.target.x();
                    viewRef.current.y = e.target.y();
                }}
            >
                {/* 
                  By separating the dots into a memoized Layer that NEVER re-renders based on focalTrack state, 
                  we eliminate the 11,000-component React lag entirely.
                */}
                <Layer>
                    {memoizedNodes}
                </Layer>

                {/* Separate Layer exclusively for the active Supernova track to guarantee shadow rendering */}
                <Layer>
                    {focalTrack && (
                        <Group x={focalTrack.x} y={focalTrack.y} listening={false}
                            ref={(node) => {
                                focalGroupRef.current = node;
                                if (node && prevFocalIdRef.current !== focalTrack.id) {
                                    prevFocalIdRef.current = focalTrack.id;
                                    // Quick pop-in animation using scale
                                    node.scale({ x: 0.3, y: 0.3 });
                                    import('konva').then((Konva) => {
                                        // Ensure node is still attached to a layer before tweening
                                        if (!node || !node.getLayer()) return;

                                        new Konva.default.Tween({
                                            node: node,
                                            scaleX: 1,
                                            scaleY: 1,
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
                                fillRadialGradientColorStops={[
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
                                fillRadialGradientColorStops={[
                                    0, '#ffffff',
                                    0.4, '#ffffff',
                                    0.7, 'rgba(150, 240, 255, 0.9)',
                                    0.9, 'rgba(0, 229, 255, 0.8)',
                                    1, 'rgba(0, 229, 255, 0)'
                                ]}
                                perfectDrawEnabled={false}
                            />
                        </Group>
                    )}
                </Layer>
            </Stage>
        </div>
    );
}
