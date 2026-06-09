import { NextResponse } from "next/server";

// POST /api/people/:id/blacklist  — body: { blacklisted: bool, reason?: string }
// (Dé)marque une personne comme étant sur liste de surveillance.
export async function POST(req, { params }) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const { id } = params;
    const body = await req.json().catch(() => ({}));

    const response = await fetch(`${backendUrl}/people/blacklist/${id}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        blacklisted: !!body.blacklisted,
        reason: body.reason ?? null,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: data?.detail || "Erreur lors du changement de statut." },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
