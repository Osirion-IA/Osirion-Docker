import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// GET /api/alerts/stats?group_id=&camera_id= → compteurs par statut (scopés) +
// état des canaux de notification.
export async function GET(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    // Transmet group_id / camera_id : sinon le compte ignore le filtre de l'écran.
    const { search } = new URL(req.url);
    const res = await fetch(`${BACKEND}/alerts/stats${search || ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ message: data?.detail || "Erreur." }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
