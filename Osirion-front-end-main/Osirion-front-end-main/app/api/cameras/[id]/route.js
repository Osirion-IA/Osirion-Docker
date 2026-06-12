import { NextResponse } from "next/server";

export async function DELETE(req, { params }) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const { id } = params;
    // Propage ?force=true (suppression en cascade côté backend).
    const force = req.nextUrl.searchParams.get("force") === "true";
    const url = `${backendUrl}/cameras/delete/${id}${force ? "?force=true" : ""}`;
    const response = await fetch(url, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de la suppression." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}

// (Dés)activation d'une caméra → backend PATCH /cameras/{id}/active.
export async function PATCH(req, { params }) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;
    const accessToken = req.cookies.get("access_token")?.value;
    if (!accessToken) {
      return NextResponse.json({ message: "Non authentifié." }, { status: 401 });
    }

    const { id } = params;
    const body = await req.json();
    const response = await fetch(`${backendUrl}/cameras/${id}/active`, {
      method: "PATCH",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: data?.detail || "Erreur lors de la mise à jour." }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ message: "Erreur serveur." }, { status: 500 });
  }
}
