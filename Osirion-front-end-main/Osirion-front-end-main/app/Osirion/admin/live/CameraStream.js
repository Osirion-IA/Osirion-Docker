import { useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';
// SOCKET_URL (Core) et MEDIAMTX_URL (vidéo WHEP) dérivés de l'hôte d'accès
// (cf. lib/publicUrls) → la vidéo + l'overlay marchent depuis tout poste du LAN.
import { SOCKET_URL, MEDIAMTX_URL } from "../../../lib/publicUrls";

// Couleur d'overlay (CSS). Visages : vert=reconnu / rouge=inconnu.
// Plaques : rouge=blacklist / cyan=connue / ambre=simplement détectée.
function detectionColor(det) {
    // Alerte (blacklist) prioritaire, quel que soit le type : rouge soutenu.
    if (det.alert) return '#dc2626';
    if (det.type === 'plate') {
        if (det.known) return '#06b6d4';
        return '#f59e0b';
    }
    return det.recognized ? '#22c55e' : '#ef4444';
}

// WHEP « non-trickle » : on attend la fin du gathering ICE avant d'envoyer
// l'offre (plafonné à timeoutMs pour les navigateurs qui ne signalent jamais
// 'complete'). Évite d'avoir à gérer le PATCH/trickle ICE.
function waitIceGatheringComplete(pc, timeoutMs) {
    if (pc.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve) => {
        const finish = () => {
            pc.removeEventListener('icegatheringstatechange', check);
            clearTimeout(timer);
            resolve();
        };
        const check = () => { if (pc.iceGatheringState === 'complete') finish(); };
        const timer = setTimeout(finish, timeoutMs);
        pc.addEventListener('icegatheringstatechange', check);
    });
}

export default function CameraStream({ cameraId, onLatencyUpdate, showStats = true }) {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const pcRef = useRef(null);
    const socketRef = useRef(null);
    const [status, setStatus] = useState('connecting');
    const [latency, setLatency] = useState(0);
    const [fps, setFps] = useState(0);
    // Les boxes plaques sont désormais dessinées CÔTÉ CLIENT (overlay canvas).
    // Ce drapeau ne sert plus qu'au badge + à la légende des couleurs.
    const [lprActive, setLprActive] = useState(false);

    // ── Vidéo WebRTC (WHEP) depuis MediaMTX ──────────────────────────────────
    useEffect(() => {
        let cancelled = false;
        let retryTimer = null;
        let resourceUrl = null;                  // ressource WHEP (DELETE au cleanup)
        const whepUrl = `${MEDIAMTX_URL}/cam${cameraId}/whep`;

        function closePc() {
            const pc = pcRef.current;
            if (pc) {
                try { pc.ontrack = null; pc.onconnectionstatechange = null; pc.close(); } catch { /* */ }
                pcRef.current = null;
            }
            const v = videoRef.current;
            if (v) { try { v.srcObject = null; } catch { /* */ } }
        }

        function scheduleRetry() {
            if (cancelled || retryTimer) return;
            retryTimer = setTimeout(() => { retryTimer = null; connect(); }, 3000);
        }

        async function connect() {
            if (cancelled) return;
            closePc();
            setStatus('connecting');
            try {
                const pc = new RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
                });
                pcRef.current = pc;
                // On ne reçoit que la vidéo (recvonly).
                pc.addTransceiver('video', { direction: 'recvonly' });

                pc.ontrack = (ev) => {
                    const v = videoRef.current;
                    if (v && ev.streams && ev.streams[0]) v.srcObject = ev.streams[0];
                };
                pc.onconnectionstatechange = () => {
                    if (cancelled) return;
                    const st = pc.connectionState;
                    if (st === 'failed' || st === 'disconnected' || st === 'closed') {
                        setStatus('error');
                        scheduleRetry();
                    }
                };

                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);
                await waitIceGatheringComplete(pc, 1500);
                if (cancelled) return;

                const res = await fetch(whepUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: pc.localDescription.sdp,
                });
                if (!res.ok) throw new Error(`WHEP HTTP ${res.status}`);
                resourceUrl = res.headers.get('Location') || null;
                const answer = await res.text();
                if (cancelled) return;
                await pc.setRemoteDescription({ type: 'answer', sdp: answer });
            } catch (e) {
                if (!cancelled) { setStatus('error'); scheduleRetry(); }
            }
        }

        connect();

        return () => {
            cancelled = true;
            if (retryTimer) clearTimeout(retryTimer);
            // Libérer la ressource WHEP côté MediaMTX (best-effort).
            if (resourceUrl) {
                const del = resourceUrl.startsWith('http')
                    ? resourceUrl : `${MEDIAMTX_URL}${resourceUrl}`;
                fetch(del, { method: 'DELETE' }).catch(() => {});
            }
            closePc();
        };
    }, [cameraId]);

    // ── Overlay : bounding boxes via Socket.IO 'metadata' ────────────────────
    useEffect(() => {
        const socket = io(SOCKET_URL, { withCredentials: true });
        socketRef.current = socket;

        let lastMetaTime = Date.now();
        let metaCount = 0;
        let fpsTimer = Date.now();

        socket.on('metadata', (data) => {
            if (data.camera_id !== cameraId) return;
            const canvas = canvasRef.current;
            if (!canvas) return;

            // Latence inter-overlay + FPS overlay (cadence d'inférence du Core)
            const now = Date.now();
            const lat = now - lastMetaTime;
            lastMetaTime = now;
            setLatency(lat);
            if (onLatencyUpdate) onLatencyUpdate(lat);
            metaCount++;
            if (now - fpsTimer >= 1000) { setFps(metaCount); metaCount = 0; fpsTimer = now; }

            // Canvas interne = repère source (width×height des frames traitées). Le
            // CSS l'étire pour recouvrir exactement la <video> (object-fit: fill),
            // donc l'alignement est automatique quelle que soit la taille d'affichage.
            const W = data.width || 640;
            const H = data.height || 480;
            if (canvas.width !== W) canvas.width = W;
            if (canvas.height !== H) canvas.height = H;

            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, W, H);

            ctx.lineWidth = Math.max(2, Math.round(W / 320));
            const fontPx = Math.max(12, Math.round(H / 24));
            ctx.font = `${fontPx}px ui-sans-serif, system-ui, sans-serif`;
            ctx.textBaseline = 'top';

            for (const det of (data.detections || [])) {
                const [x1, y1, x2, y2] = det.bbox;
                const color = detectionColor(det);
                ctx.strokeStyle = color;
                ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

                const label = det.label || '';
                if (label) {
                    const padX = 4, padY = 3;
                    const tw = ctx.measureText(label).width;
                    const bh = fontPx + padY * 2;
                    let ly = y1 - bh;
                    if (ly < 0) ly = y1;       // box collée au bord haut → étiquette à l'intérieur
                    ctx.fillStyle = color;
                    ctx.fillRect(x1, ly, tw + padX * 2, bh);
                    ctx.fillStyle = '#000';
                    ctx.fillText(label, x1 + padX, ly + padY);
                }
            }
        });

        // S'abonner aux métadonnées de cette caméra.
        socket.emit('start_stream', { camera_id: cameraId });

        return () => {
            socket.emit('stop_stream');
            socket.disconnect();
            const canvas = canvasRef.current;
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx && ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        };
    }, [cameraId]);

    // Poll léger de l'état LPR du Core (badge + légende). Rafraîchi toutes les 15s.
    useEffect(() => {
        let active = true;
        const fetchLpr = async () => {
            try {
                const res = await fetch(`${SOCKET_URL}/api/lpr/status`);
                if (!res.ok) return;
                const data = await res.json();
                if (active) setLprActive(!!data.lpr_enabled);
            } catch { /* Core injoignable : ignorer */ }
        };
        fetchLpr();
        const id = setInterval(fetchLpr, 15000);
        return () => { active = false; clearInterval(id); };
    }, []);

    const latencyColor =
        latency === 0 ? 'text-gray-400' :
        latency < 150 ? 'text-emerald-400' :
        latency < 350 ? 'text-yellow-400' :
        'text-red-400';

    return (
        <div className="relative w-full h-full bg-gray-950 overflow-hidden">
            {/* Vidéo WebRTC — décodage natif accéléré. object-fill : même étirement
                que le canvas d'overlay → bounding boxes parfaitement alignées. */}
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                onPlaying={() => setStatus('live')}
                className="absolute inset-0 w-full h-full object-fill"
            />

            {/* Canvas transparent superposé — overlay des bounding boxes côté client */}
            <canvas
                ref={canvasRef}
                width={640}
                height={480}
                className="absolute inset-0 w-full h-full pointer-events-none"
            />

            {/* État connexion */}
            {status !== 'live' && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-gray-950">
                    {status === 'connecting' ? (
                        <>
                            <div className="h-9 w-9 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                            <span className="text-white/50 text-sm font-medium">Connexion vidéo (WebRTC)…</span>
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

            {/* Badge LPR + légende des couleurs de plaques (overlay dessiné côté client) */}
            {status === 'live' && lprActive && (
                <div className="absolute top-3 left-3 flex flex-col gap-1">
                    <div className="px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm text-xs font-semibold text-amber-300 flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" /> LPR actif
                    </div>
                    <div className="px-2 py-1 rounded-md bg-black/50 backdrop-blur-sm text-[10px] text-white/80 leading-tight space-y-0.5">
                        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: '#f59e0b' }} /> Plaque détectée</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: '#06b6d4' }} /> Plaque connue</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: '#ef4444' }} /> Blacklist (alerte)</div>
                    </div>
                </div>
            )}

            {/* HUD : latence + cadence d'overlay (mises à jour de bounding boxes /s) */}
            {showStats && status === 'live' && (
                <div className="absolute bottom-3 right-3 flex items-center gap-2">
                    <div className={`px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm text-xs font-mono font-semibold ${latencyColor}`}>
                        {latency}ms
                    </div>
                    <div className="px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-sm text-xs font-mono font-semibold text-white/70">
                        {fps} ovl/s
                    </div>
                </div>
            )}
        </div>
    );
}
