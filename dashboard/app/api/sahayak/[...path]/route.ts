import { NextRequest, NextResponse } from "next/server";

const API_PREFIX = "/api/sahayak";

function backendUrl(request: NextRequest) {
  const base =
    process.env.SAHAYAK_API_URL ||
    process.env.NEXT_PUBLIC_SAHAYAK_API_URL ||
    "http://localhost:8000";
  const path = request.nextUrl.pathname.slice(API_PREFIX.length) || "/";
  return `${base.replace(/\/$/, "")}${path}${request.nextUrl.search}`;
}

async function proxy(request: NextRequest) {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  if (contentType) {
    headers.set("content-type", contentType);
  }
  headers.set("x-request-id", requestId);
  headers.set("x-sahayak-role", "admin");
  if (process.env.SAHAYAK_DASHBOARD_API_KEY) {
    headers.set("x-sahayak-api-key", process.env.SAHAYAK_DASHBOARD_API_KEY);
  }

  const method = request.method.toUpperCase();
  const response = await fetch(backendUrl(request), {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : await request.text(),
    cache: "no-store"
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      "x-request-id": response.headers.get("x-request-id") || requestId
    }
  });
}

export async function GET(request: NextRequest) {
  return proxy(request);
}

export async function POST(request: NextRequest) {
  return proxy(request);
}

export async function PATCH(request: NextRequest) {
  return proxy(request);
}

export async function PUT(request: NextRequest) {
  return proxy(request);
}

export async function DELETE(request: NextRequest) {
  return proxy(request);
}
