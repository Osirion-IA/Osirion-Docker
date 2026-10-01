import { NextResponse } from "next/server";

// Liste des groupes de caméras → backend GET /groups/
export async function GET(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Aucun access_token." }, { status: 401 });
    }

    const response = await fetch(`${backendUrl}/groups/`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de la récupération des groupes." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

// Création d'un groupe → backend POST /groups/
export async function POST(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const body = await req.json();
    const response = await fetch(`${backendUrl}/groups/`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de la création du groupe." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
