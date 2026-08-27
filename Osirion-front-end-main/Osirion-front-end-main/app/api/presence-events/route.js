import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

export async function GET(req) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const url = new URL(req.url);
    const response = await fetch(`${BACKEND}/events/presence-history?${url.searchParams.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { message: data?.detail || "Impossible de charger l’historique de présence." },
        { status: response.status },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
