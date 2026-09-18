import { api } from "./api";

export async function registerUser(firstName, lastName, email, password) {
  const data = await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      first_name: firstName,
      last_name: lastName,
      email,
      password,
    }),
  });
  if (data?.access_token) {
    localStorage.setItem("token", data.access_token);
  }
  return data;
}

export async function loginUser(email, password) {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (data?.access_token) {
    localStorage.setItem("token", data.access_token);
  }
  return data;
}

export async function getProfile() {
  return await api("/auth/me");
}

export function logoutUser() {
  localStorage.removeItem("token");
}

export async function loginWithGoogle(credential) {
  const data = await api("/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });
  if (data?.access_token) {
    localStorage.setItem("token", data.access_token);
  }
  return data;
}

export async function getGoogleClientId() {
  const data = await api("/auth/google/client-id");
  return data.client_id;
}
