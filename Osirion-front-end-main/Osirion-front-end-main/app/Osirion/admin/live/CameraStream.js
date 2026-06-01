import { useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:5000";

export default function CameraStream({ cameraId, onLatencyUpdate, showStats = true }) {
    const canvasRef = useRef(null);
    const socketRef = useRef(null);
    const [status, setStatus] = useState('connecting');
    const [latency, setLatency] = useState(0);
    const [fps, setFps] = useState(0);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');

        let pendingImg = null;
        let pendingSeq = 0;
        let renderedSeq = 0;
        let animId = null;
        let lastFrameTime = Date.now();
        let frameCount = 0;
        let fpsTimer = Date.now();

        function renderLoop() {
            if (pendingImg && ctx) {
                ctx.drawImage(pendingImg, 0, 0, 640, 480);
                pendingImg = null;
                frameCount++;
            }
            animId = requestAnimationFrame(renderLoop);
        }
        animId = requestAnimationFrame(renderLoop);

        const socket = io(SOCKET_URL, { withCredentials: true });
        socketRef.current = socket;

        socket.on('connect', () => setStatus('connecting'));
        socket.on('stream_started', () => setStatus('live'));
        socket.on('disconnect', () => setStatus('error'));

        socket.on('frame', (data) => {
            if (data.camera_id !== cameraId) return;

            const now = Date.now();
            const lat = now - lastFrameTime;
            lastFrameTime = now;
            setLatency(lat);
            if (onLatencyUpdate) onLatencyUpdate(lat);

            // Calcul FPS glissant toutes les secondes
            if (now - fpsTimer >= 1000) {
                setFps(frameCount);
                frameCount = 0;
                fpsTimer = now;
            }

            const seq = ++pendingSeq;
            const img = new window.Image();
            img.onload = () => {
                if (seq > renderedSeq) {
                    renderedSeq = seq;
                    pendingImg = img;
                    setStatus((prev) => prev !== 'live' ? 'live' : prev);
                }
            };
            img.src = 'data:image/jpeg;base64,' + data.data;
        });

        socket.emit('start_stream', { camera_id: cameraId });

        return () => {
            cancelAnimationFrame(animId);
            pendingImg = null;
            socket.emit('stop_stream');
            socket.disconnect();
        };
    }, [cameraId]);

    const latencyColor =
        latency === 0 ? 'text-gray-400' :
        latency < 100 ? 'text-emerald-400' :
        latency < 250 ? 'text-yellow-400' :
        'text-red-400';

    return (
        <div className="relative w-full h-full bg-gray-950 overflow-hidden">
            {/* État connexion */}
            {status !== 'live' && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-gray-950">
                    {status === 'connecting' ? (
                        <>
                            <div className="h-9 w-9 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                            <span className="text-white/50 text-sm font-medium">Connexion en cours…</span>
                        </>
                    ) : (
                        <>
                            <svg className="h-10 w-10 text-red-500/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M18.364 5.636a9 9 0 1 1-12.728 0M12 2v6" />
                            </svg>
                            <span className="text-white/50 text-sm font-medium">Signal perdu</span>
                        </>
                    )}
                </div>
            )}

            {/* Canvas — remplit le conteneur, ratio conservé par le parent */}
            <canvas
                ref={canvasRef}
                width={640}
                height={480}
                className="absolute inset-0 w-full h-full"
            />

            {/* HUD : latence + FPS */}
            {showStats && status === 'live' && (
                <div className="absolute bottom-3 right-3 flex items-center gap-2">
                    <div className={`px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm text-xs font-mono font-semibold ${latencyColor}`}>
                        {latency}ms
                    </div>
                    <div className="px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm text-xs font-mono font-semibold text-white/70">
                        {fps} fps
                    </div>
                </div>
            )}
        </div>
    );
}
