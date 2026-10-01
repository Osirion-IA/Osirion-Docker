import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// GET /api/zones?camera_id=<id>  → liste des zones (polygones) d'une caméra.
export async function GET(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const camId = req.nextUrl.searchParams.get("camera_id");
  const q = camId ? `?camera_id=${encodeURIComponent(camId)}` : "";
  try {
    const res = await fetch(`${BACKEND}/zones/${q}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

// POST /api/zones  → crée une zone.
export async function POST(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND}/zones/add`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
