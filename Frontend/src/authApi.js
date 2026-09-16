import { api } from "./api";

export async function registerUser(email, password) {
  return await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
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