import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

function getToken(req) {
  return req.cookies.get("access_token")?.value;
}

export async function GET(req) {
  const token = getToken(req);
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const { searchParams } = new URL(req.url);
    const limit = searchParams.get("limit") || "50";

    const [eventsRes, camerasRes] = await Promise.all([
      fetch(`${BACKEND}/events/?limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${BACKEND}/cameras/`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ]);

    if (!eventsRes.ok) {
      const d = await eventsRes.json().catch(() => ({}));
      return NextResponse.json({ message: d?.detail || "Erreur récupération événements." }, { status: eventsRes.status });
    }

    const [events, cameras] = await Promise.all([
      eventsRes.json(),
      camerasRes.ok ? camerasRes.json() : [],
    ]);

    const cameraMap = Object.fromEntries((Array.isArray(cameras) ? cameras : []).map((c) => [c.id, c]));

    const enriched = (Array.isArray(events) ? events : []).map((event) => ({
      ...event,
      camera_nom: cameraMap[event.camera_id]?.cam_name || `CAM-${event.camera_id}`,
      camera_location: cameraMap[event.camera_id]?.location || "—",
    }));

    return NextResponse.json(enriched);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
