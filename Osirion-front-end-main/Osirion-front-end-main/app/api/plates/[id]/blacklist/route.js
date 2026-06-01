import { NextResponse } from "next/server";

// POST /api/plates/:id/blacklist?blacklisted=true|false
// (Dé)marque un véhicule comme blacklisté.
export async function POST(req, { params }) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const { id } = params;
    const { searchParams } = new URL(req.url);
    const blacklisted = searchParams.get("blacklisted") === "false" ? "false" : "true";

    const response = await fetch(
      `${backendUrl}/plates/blacklist/${id}?blacklisted=${blacklisted}`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      }
    );

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: data?.detail || "Erreur lors du changement de statut blacklist." },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
