import { NextResponse } from "next/server";

// GET /api/plates  → liste des véhicules / plaques connues
export async function GET(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Aucun access_token." }, { status: 401 });
    }

    const { searchParams } = new URL(req.url);
    const qs = searchParams.get("blacklisted_only") === "true" ? "?blacklisted_only=true" : "";

    const response = await fetch(`${backendUrl}/plates/${qs}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: data?.detail || "Erreur lors de la récupération des plaques." },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

// POST /api/plates  → ajouter une plaque
export async function POST(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const body = await req.json();
    const response = await fetch(`${backendUrl}/plates/add`, {
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
        { message: data?.detail || "Erreur lors de l'ajout de la plaque." },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
