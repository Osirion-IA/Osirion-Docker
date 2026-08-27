import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// PUT /api/work-schedules/<id>  → met à jour un régime horaire.
export async function PUT(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const { id } = await params;
  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND}/work-schedules/${id}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

// DELETE /api/work-schedules/<id>  → supprime un régime.
// `force` est relayé : sans lui, le backend refuse (409) un régime encore utilisé
// par des zones, qui cesseraient sinon d'être surveillées sans prévenir.
export async function DELETE(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const { id } = await params;
  const force = req.nextUrl.searchParams.get("force");
  const q = force ? `?force=${encodeURIComponent(force)}` : "";
  try {
    const res = await fetch(`${BACKEND}/work-schedules/${id}${q}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
