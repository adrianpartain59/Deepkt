"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { Stage, Layer, Circle, Group } from "react-konva";
import { FaSoundcloud, FaChevronDown, FaChevronRight } from "react-icons/fa";

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
    const [scale, setScale] = useState(1.5); // Start slightly zoomed in
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [focalTrack, setFocalTrack] = useState<UniverseNode | null>(null);

    // Search State
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string }[]>([]);
    const [isSearching, setIsSearching] = useState(false);

    // Sidebar State
    const [neighbors, setNeighbors] = useState<{ id: string, artist: string, title: string, x: number, y: number, url?: string }[]>([]);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    // Refs for imperative high-speed math without triggering React renders
    const nodesRef = useRef<UniverseNode[]>([]);
    const viewRef = useRef({ x: 0, y: 0, scale: 1.5 });
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
                // We will scale them up by * 2000 to spread them across a ~30,000px virtual map
                // to explicitly enforce wide spacing and prevent node density overlapping.
                const scaled = data.map((n: any) => ({
                    ...n,
                    x: n.x * 2000,
                    y: n.y * 2000,
                }));
                setNodes(scaled);
                nodesRef.current = scaled;
                // Auto-center camera precisely on the very first node so user doesn't spawn in empty space
                if (scaled.length > 0) {
                    const first = scaled[0];
                    const cx = window.innerWidth / 2;
                    const cy = window.innerHeight / 2;
                    const startX = cx - first.x * 1.5;
                    const startY = cy - first.y * 1.5;
                    setPosition({ x: startX, y: startY });
                    viewRef.current.x = startX;
                    viewRef.current.y = startY;
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

    // 3. Zoom Logic (Mouse Wheel)
    const handleWheel = (e: any) => {
        e.evt.preventDefault();
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

        const clampedScale = Math.min(Math.max(newScale, 0.8), 3.0);

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
        fetch(`http://127.0.0.1:8000/api/neighbors/${focalTrack.id}`)
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
        const targetScale = 1.6;
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
                const targetScale = 1.6;
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
            {/* Bloom/Glow (Hit area is implicitly the union of children, or we can add a specific hit circle) */}
            <Circle
                radius={20} // Widened from 8 to 20
                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                fillRadialGradientStartRadius={0}
                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                fillRadialGradientEndRadius={10} // Widened from 8 to 20
                fillRadialGradientColorStops={[
                    0, 'rgba(255, 255, 255, 0.5)',
                    0.3, 'rgba(255, 255, 255, 0.2)',
                    1, 'rgba(255, 255, 255, 0)'
                ]}
                perfectDrawEnabled={false}
                listening={true}
                hitFunc={(context, shape) => {
                    context.beginPath();
                    context.arc(0, 0, 15, 0, Math.PI * 2, true);
                    context.closePath();
                    context.fillStrokeShape(shape);
                }}
            />
            {/* Core */}
            <Circle
                radius={2.5}
                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                fillRadialGradientStartRadius={0}
                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                fillRadialGradientEndRadius={2.5}
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
        <div className="absolute inset-0 bg-black cursor-grab active:cursor-grabbing">

            {/* HUD Fixed Overlay */}
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none flex flex-col items-center">
                <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-[#e040fb] to-[#00e5ff] uppercase tracking-wider title-glow">
                    AMBYS
                </h1>
                <p className="text-center text-xs text-zinc-500 font-mono mt-1 mb-8">
                    {nodes.length > 0 ? `${nodes.length} nodes active` : 'Initializing Map...'}
                </p>

                {/* Focal Track Display */}
                {focalTrack && (
                    <div className="bg-black/80 backdrop-blur-md border border-[#e040fb]/30 p-3 rounded-xl flex flex-col items-center animate-in fade-in slide-in-from-top-4 duration-300 w-[32rem] shadow-[0_0_30px_rgba(224,64,251,0.2)]">
                        <p className="text-[10px] text-[#00e5ff] uppercase tracking-widest font-bold mb-1">Focal Track</p>
                        <h2 className="text-xl font-bold text-white text-center w-full truncate">{focalTrack.title}</h2>
                        <h3 className="text-sm text-zinc-400 text-center w-full truncate">{focalTrack.artist}</h3>
                    </div>
                )}
            </div>

            {/* Top Right: Search Bar */}
            <div className="absolute top-6 right-6 z-20 w-80">
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
                        <div className="max-h-[50vh] overflow-y-auto">
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
                                if (node && prevFocalIdRef.current !== focalTrack.id) {
                                    prevFocalIdRef.current = focalTrack.id;
                                    // Quick pop-in animation using scale
                                    node.scale({ x: 0.3, y: 0.3 });
                                    import('konva').then((Konva) => {
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
                                radius={40}
                                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                                fillRadialGradientStartRadius={1}
                                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                                fillRadialGradientEndRadius={40}
                                fillRadialGradientColorStops={[
                                    0, 'rgba(0, 229, 255, 0.8)',
                                    0.4, 'rgba(0, 229, 255, 0.3)',
                                    1, 'rgba(0, 229, 255, 0)'
                                ]}
                                perfectDrawEnabled={false}
                            />
                            {/* Core */}
                            <Circle
                                radius={15} // Slightly larger to allow for a softer grade
                                fillRadialGradientStartPoint={{ x: 0, y: 0 }}
                                fillRadialGradientStartRadius={0}
                                fillRadialGradientEndPoint={{ x: 0, y: 0 }}
                                fillRadialGradientEndRadius={15}
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
