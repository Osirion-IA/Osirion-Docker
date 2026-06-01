import { NextResponse } from "next/server";

// POST /api/plates/search  → recherche floue (fuzzy) d'une plaque OCR
// Body: { plate_text, threshold?, k? }
export async function POST(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const body = await req.json();
    const response = await fetch(`${backendUrl}/plates/search`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: data?.detail || "Erreur lors de la recherche." },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
