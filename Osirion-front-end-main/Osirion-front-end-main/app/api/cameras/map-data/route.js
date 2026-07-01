import { NextResponse } from "next/server";

// Flux carte OpenStreetMap / Leaflet → backend GET /cameras/map-data
// Renvoie uniquement les caméras actives ET géolocalisées (id, name, lat, lng,
// bearing, active_modules) — aucun secret exposé.
export async function GET(req) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Aucun access_token." }, { status: 401 });
    }

    const response = await fetch(`${backendUrl}/cameras/map-data`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de la récupération des données carte." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
