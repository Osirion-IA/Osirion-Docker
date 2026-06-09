import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// POST /api/maintenance/purge?days=N → purge MANUELLE des événements anciens (admin).
export async function POST(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const { searchParams } = new URL(req.url);
    const days = searchParams.get("days") || "90";
    const res = await fetch(`${BACKEND}/maintenance/purge-events?days=${encodeURIComponent(days)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ message: data?.detail || "Erreur." }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
