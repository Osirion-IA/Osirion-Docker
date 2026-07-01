import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

function getToken(req) {
  return req.cookies.get("access_token")?.value;
}

export async function GET(req) {
  const token = getToken(req);
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const res = await fetch(`${BACKEND}/people/list/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ message: data?.detail || "Erreur." }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

export async function POST(req) {
  const token = getToken(req);
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });

  try {
    const formData = await req.formData();
    // ≥2 photos → champ "images" (endpoint multi) ; sinon "image_url" (endpoint mono).
    const isMulti = formData.getAll("images").length > 0;
    const endpoint = isMulti ? "/people/upload/multi/" : "/people/upload/";
    const res = await fetch(`${BACKEND}${endpoint}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ message: data?.error || data?.detail || "Erreur." }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
