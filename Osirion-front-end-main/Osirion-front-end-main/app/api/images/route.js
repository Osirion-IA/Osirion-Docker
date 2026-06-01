import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const path = searchParams.get("path");

  if (!path) return new NextResponse("Paramètre path manquant.", { status: 400 });

  // Empêche le path traversal
  const safe = path.replace(/\.\./g, "").replace(/^\/+/, "");
  if (!safe) return new NextResponse("Chemin invalide.", { status: 400 });

  try {
    const res = await fetch(`${BACKEND}/${safe}`);
    if (!res.ok) return new NextResponse("Image introuvable.", { status: 404 });

    const buffer = await res.arrayBuffer();
    const contentType = res.headers.get("content-type") || "image/jpeg";

    return new NextResponse(buffer, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=86400, immutable",
      },
    });
  } catch {
    return new NextResponse("Erreur serveur.", { status: 500 });
  }
}
