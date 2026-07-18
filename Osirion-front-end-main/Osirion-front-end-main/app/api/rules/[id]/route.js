import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

export async function PUT(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const { id } = await params;
  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND}/rules/${id}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

export async function DELETE(req, { params }) {
  const token = req.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
  const { id } = await params;
  try {
    const res = await fetch(`${BACKEND}/rules/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
