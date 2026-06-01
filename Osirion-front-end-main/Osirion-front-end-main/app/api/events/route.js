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

    const [eventsRes, camerasRes, peopleRes] = await Promise.all([
      fetch(`${BACKEND}/events/?limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${BACKEND}/cameras/`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${BACKEND}/people/list/`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ]);

    if (!eventsRes.ok) {
      const d = await eventsRes.json().catch(() => ({}));
      return NextResponse.json({ message: d?.detail || "Erreur récupération événements." }, { status: eventsRes.status });
    }

    const [events, cameras, people] = await Promise.all([
      eventsRes.json(),
      camerasRes.ok ? camerasRes.json() : [],
      peopleRes.ok ? peopleRes.json() : [],
    ]);

    const cameraMap = Object.fromEntries((Array.isArray(cameras) ? cameras : []).map((c) => [c.id, c]));
    const peopleMap = Object.fromEntries(
      (Array.isArray(people) ? people : []).filter((p) => p.id).map((p) => [p.id, p])
    );

    const enriched = (Array.isArray(events) ? events : []).map((event) => ({
      ...event,
      camera_nom: cameraMap[event.camera_id]?.cam_name || `CAM-${event.camera_id}`,
      camera_location: cameraMap[event.camera_id]?.location || "—",
      person_nom:
        event.person_id && peopleMap[event.person_id]
          ? `${peopleMap[event.person_id].first_name} ${peopleMap[event.person_id].last_name}`
          : null,
    }));

    return NextResponse.json(enriched);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
