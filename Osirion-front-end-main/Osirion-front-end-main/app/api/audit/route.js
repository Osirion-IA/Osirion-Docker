import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// GET /api/audit?action=...  → journal d'audit (admin).
export async function GET(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const { searchParams } = new URL(req.url);
    const action = searchParams.get("action");
    const qs = action ? `?action=${encodeURIComponent(action)}` : "";
    const res = await fetch(`${BACKEND}/audit/${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ message: data?.detail || "Erreur." }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
