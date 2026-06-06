import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://backend:8000";

async function proxy(request: NextRequest, method: string) {
  const pathParts = request.nextUrl.pathname.replace("/api", "");
  const search = request.nextUrl.search;
  const url = `${BACKEND_URL}${pathParts}${search}`;

  const headers: HeadersInit = {};

  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers["content-type"] = contentType;
  }

  let body: BodyInit | null | undefined;

  if (contentType?.includes("multipart/form-data")) {
    body = await request.formData();
    delete headers["content-type"];
  } else if (method !== "GET" && method !== "HEAD") {
    body = await request.text();
  }

  const response = await fetch(url, {
    method,
    headers,
    body,
    redirect: "follow" as RequestRedirect,
  });

  const responseHeaders = new Headers();
  response.headers.forEach((value, key) => {
    if (key !== "content-encoding" && key !== "transfer-encoding") {
      responseHeaders.set(key, value);
    }
  });

  const data = await response.arrayBuffer();

  return new NextResponse(data, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest) {
  return proxy(request, "GET");
}

export async function POST(request: NextRequest) {
  return proxy(request, "POST");
}

export async function PUT(request: NextRequest) {
  return proxy(request, "PUT");
}

export async function DELETE(request: NextRequest) {
  return proxy(request, "DELETE");
}

export async function PATCH(request: NextRequest) {
  return proxy(request, "PATCH");
}
