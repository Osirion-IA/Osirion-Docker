import { NextResponse } from "next/server";

export async function GET(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Aucun access_token." }, { status: 401 });
    }

    // Propage le filtre optionnel ?group_id=<id> vers le backend.
    const groupId = req.nextUrl.searchParams.get("group_id");
    const query = groupId ? `?group_id=${encodeURIComponent(groupId)}` : "";
    const response = await fetch(`${backendUrl}/cameras/${query}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      // On RELAIE le code du backend au lieu de tout aplatir en 500 : un refus
      // d'autorisation (403) se présentait comme une panne serveur, ce qui rend
      // indébogable la restriction d'un rôle.
      return NextResponse.json(
        { message: data?.detail || data?.message || "Erreur lors de la récupération des caméras." },
        { status: response.status },
      );
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

export async function POST(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const body = await req.json();
    const response = await fetch(`${backendUrl}/cameras/add`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de l'ajout." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
