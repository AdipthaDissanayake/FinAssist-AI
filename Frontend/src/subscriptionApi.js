import { api } from "./api";

export function getSubscription() {
  return api("/api/subscription");
}

export function getPublicPlans() {
  return api("/api/subscription/plans");
}

export function getSubscriptionUsage() {
  return api("/api/subscription/usage");
}

export function simulateSubscriptionChange(planCode, { paymentMethodId = null, cardDetails = null } = {}) {
  const payload = { plan_code: planCode };
  if (paymentMethodId) {
    payload.payment_method_id = paymentMethodId;
  }
  if (cardDetails) {
    payload.card_details = cardDetails;
  }
  return api("/api/subscription/simulate-change", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPaymentMethods() {
  return api("/api/subscription/payment-methods");
}

export function addPaymentMethod(cardData) {
  return api("/api/subscription/payment-methods", {
    method: "POST",
    body: JSON.stringify(cardData),
  });
}

export function deletePaymentMethod(paymentMethodId) {
  return api(`/api/subscription/payment-methods/${paymentMethodId}`, {
    method: "DELETE",
  });
}

export function cancelSubscription() {
  return api("/api/subscription/cancel", {
    method: "POST",
  });
}

