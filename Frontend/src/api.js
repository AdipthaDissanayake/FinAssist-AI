export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    throw new ApiError("Network error. Please check your connection and try again.", 0);
  }

  const rawBody = await response.text();
  let payload = null;
  try {
    payload = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    if (!response.ok) throw new ApiError(`The server returned an error (${response.status}). Please try again shortly.`, response.status);
    throw new ApiError("The server returned an unexpected response. Please refresh and try again.", response.status);
  }

  if (!response.ok) {
    const message = typeof payload?.detail === "string"
      ? payload.detail
      : typeof payload?.message === "string"
        ? payload.message
        : "Request failed. Please try again.";
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

