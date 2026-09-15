import { api } from "./api";

export function getSubscription() {
  return api("/api/subscription");
}

export function getSubscriptionUsage() {
  return api("/api/subscription/usage");
}

export function simulateSubscriptionChange(planCode) {
  return api("/api/subscription/simulate-change", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode }),
  });
}
