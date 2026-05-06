import { NextRequest, NextResponse } from "next/server";

const API_PREFIX = "/api/sahayak";

function envFlag(value: string | undefined, fallback: boolean) {
  if (value === undefined || value === "") {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function backendUrl(request: NextRequest) {
  const base =
    process.env.SAHAYAK_API_URL ||
    process.env.NEXT_PUBLIC_SAHAYAK_API_URL ||
    "http://localhost:8000";
  const path = request.nextUrl.pathname.slice(API_PREFIX.length) || "/";
  return `${base.replace(/\/$/, "")}${path}${request.nextUrl.search}`;
}

function dashboardKeyFrom(request: NextRequest) {
  const headerKey = request.headers.get("x-sahayak-dashboard-key");
  if (headerKey) {
    return headerKey.trim();
  }
  const authorization = request.headers.get("authorization") || "";
  if (authorization.toLowerCase().startsWith("bearer ")) {
    return authorization.slice(7).trim();
  }
  return "";
}

function dashboardAccessAllowed(request: NextRequest) {
  const serverKeys = [
    process.env.SAHAYAK_DASHBOARD_API_KEY,
    process.env.DASHBOARD_ADMIN_KEY,
    process.env.DASHBOARD_READONLY_KEY
  ].filter(Boolean);
  const authRequired = envFlag(
    process.env.SAHAYAK_DASHBOARD_UI_AUTH_REQUIRED || process.env.DASHBOARD_AUTH_REQUIRED,
    serverKeys.length > 0
  );
  if (!authRequired) {
    return true;
  }
  const providedKey = dashboardKeyFrom(request);
  return Boolean(providedKey && serverKeys.some((key) => key === providedKey));
}

async function proxy(request: NextRequest) {
  if (!dashboardAccessAllowed(request)) {
    return NextResponse.json(
      {
        error: "dashboard_auth_required",
        detail: "Enter the dashboard access key to continue."
      },
      { status: 401 }
    );
  }

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
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(backendUrl(request), {
      method,
      headers,
      body: method === "GET" || method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: controller.signal
    });

    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
        "x-request-id": response.headers.get("x-request-id") || requestId
      }
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "sahayak_backend_unavailable",
        detail: error instanceof Error ? error.message : "Backend request failed"
      },
      {
        status: 502,
        headers: {
          "x-request-id": requestId
        }
      }
    );
  } finally {
    clearTimeout(timeout);
  }
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
