import { useEffect, useState } from "react";
import { ApiError } from "./api";
import { getSubscription, getSubscriptionUsage, simulateSubscriptionChange } from "./subscriptionApi";

// Keep this catalogue synchronized with Backend.subscription_service.DEFAULT_PLANS
// until the backend exposes a plan-catalogue endpoint.
const PLANS = Object.freeze([
  { code: "free", name: "Free", price: 0, limit: 5, description: "For trying source-backed financial research." },
  { code: "basic", name: "Basic", price: 499, limit: 50, description: "For regular financial research and learning." },
  { code: "premium", name: "Premium", price: 999, limit: 200, description: "For higher-volume research needs." },
]);
const PLAN_BY_CODE = new Map(PLANS.map((plan) => [plan.code, plan]));
const SUBSCRIPTION_STATUSES = new Set(["active", "cancelled", "expired"]);

export default function SubscriptionPage({ quotaLimitReached = false, onDismissQuotaLimit }) {
  const [subscription, setSubscription] = useState(null);
  const [usage, setUsage] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isChanging, setIsChanging] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");

  async function refreshSubscription() {
    setIsLoading(true);
    setError(null);
    try {
      const [subscriptionData, usageData] = await Promise.all([getSubscription(), getSubscriptionUsage()]);
      validateSubscription(subscriptionData);
      validateUsage(usageData);
      validateSubscriptionUsageConsistency(subscriptionData, usageData);
      setSubscription(subscriptionData);
      setUsage(usageData);
    } catch (requestError) {
      setError(toDisplayError(requestError));
      setSubscription(null);
      setUsage(null);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { refreshSubscription(); }, []);

  async function changePlan(planCode) {
    if (!subscription || planCode === subscription.current_plan || isChanging) return;
    setIsChanging(true);
    setError(null);
    setNotice("");
    try {
      const result = await simulateSubscriptionChange(planCode);
      const scheduledPlan = validatePlanChangeResponse(result, planCode);
      setNotice(scheduledPlan
        ? `${planLabel(scheduledPlan)} is scheduled for your next billing period. Your current plan remains active until then; no payment was processed.`
        : `${planLabel(planCode)} is now active. This is a simulation only; no payment was processed.`);
      await refreshSubscription();
    } catch (requestError) {
      setError(toDisplayError(requestError));
    } finally {
      setIsChanging(false);
    }
  }

  if (isLoading) return <SubscriptionLoading />;

  return <section className="subscription-page" aria-labelledby="subscription-title">
    <div className="subscription-page-heading">
      <div>
        <p className="eyebrow">SUBSCRIPTION</p>
        <h2 id="subscription-title">Your plan and usage</h2>
        <p>Manage your monthly financial-analysis allowance.</p>
      </div>
      <button className="subscription-refresh" type="button" onClick={refreshSubscription}>Refresh</button>
    </div>

    <p className="simulation-notice">Simulation — No real payment is processed.</p>
    {quotaLimitReached && <QuotaLimitNotice onDismiss={onDismissQuotaLimit} />}
    {notice && <div className="subscription-notice" role="status">{notice}</div>}
    {error && <SubscriptionError error={error} onRetry={refreshSubscription} />}

    {!error && subscription && usage && <>
      <div className="subscription-overview">
        <CurrentSubscriptionCard subscription={subscription} />
        <UsageCard usage={usage} />
      </div>
      <section className="pricing-section" aria-labelledby="plans-title">
        <div className="section-heading">
          <div><p className="eyebrow">PLANS</p><h3 id="plans-title">Choose the right allowance</h3></div>
          <p>Changes are simulated for this academic project.</p>
        </div>
        <div className="plan-grid">
          {PLANS.map((plan) => <PlanCard
            key={plan.code}
            plan={plan}
            currentPlan={subscription.current_plan}
            onChange={changePlan}
            isChanging={isChanging}
          />)}
        </div>
      </section>
    </>}
  </section>;
}

function CurrentSubscriptionCard({ subscription }) {
  return <section className="subscription-card current-subscription-card" aria-labelledby="current-plan-title">
    <div className="card-heading"><p className="eyebrow">CURRENT SUBSCRIPTION</p><span className="subscription-status">{subscription.subscription_status}</span></div>
    <h3 id="current-plan-title">{subscription.plan_name}</h3>
    <p className="plan-price">{formatLkr(subscription.price_lkr)}<span>/month</span></p>
    <dl className="subscription-details">
      <div><dt>Billing period</dt><dd>{formatDate(subscription.current_period_start)} – {formatDate(subscription.current_period_end)}</dd></div>
      <div><dt>Monthly allowance</dt><dd>{subscription.monthly_analysis_limit} analyses</dd></div>
    </dl>
  </section>;
}

function UsageCard({ usage }) {
  const percent = usage.monthly_analysis_limit > 0
    ? Math.min(100, Math.round((usage.used / usage.monthly_analysis_limit) * 100))
    : 0;
  return <section className="subscription-card usage-card" aria-labelledby="usage-title">
    <p className="eyebrow">MONTHLY USAGE</p>
    <h3 id="usage-title">{usage.used} / {usage.monthly_analysis_limit} analyses used</h3>
    <div className="usage-progress" role="progressbar" aria-label="Monthly analysis usage" aria-valuemin="0" aria-valuemax={usage.monthly_analysis_limit} aria-valuenow={usage.used}>
      <span style={{ width: `${percent}%` }} />
    </div>
    <div className="usage-summary"><strong>{usage.remaining}</strong><span>analyses remaining this billing period</span></div>
  </section>;
}

function PlanCard({ plan, currentPlan, onChange, isChanging }) {
  const isCurrent = plan.code === currentPlan;
  const current = PLANS.find((item) => item.code === currentPlan);
  const label = isCurrent ? "Current Plan" : plan.price > (current?.price ?? 0) ? "Upgrade" : "Change Plan";
  return <article className={`plan-card ${isCurrent ? "current" : ""}`}>
    {isCurrent && <span className="current-plan-badge">Current plan</span>}
    <p className="plan-name">{plan.name}</p>
    <p className="plan-price">{formatLkr(plan.price)}<span>/month</span></p>
    <p className="plan-allowance">{plan.limit} analyses/month</p>
    <p className="plan-description">{plan.description}</p>
    <button className="plan-action" type="button" disabled={isCurrent || isChanging} onClick={() => onChange(plan.code)}>
      {isChanging && !isCurrent ? "Updating…" : label}
    </button>
  </article>;
}

function SubscriptionError({ error, onRetry }) {
  return <div className="subscription-error" role="alert">
    <div><strong>{error.title}</strong><p>{error.message}</p></div>
    <button type="button" onClick={onRetry}>Try again</button>
  </div>;
}

function QuotaLimitNotice({ onDismiss }) {
  return <div className="subscription-error quota-limit-notice" role="alert">
    <div><strong>Monthly analysis limit reached</strong><p>Your analysis request was not completed because all analyses for this billing period have been used. Choose an upgrade or plan change below to continue.</p></div>
    <button type="button" onClick={onDismiss}>Dismiss</button>
  </div>;
}

function SubscriptionLoading() {
  return <section className="subscription-page" aria-label="Loading subscription">
    <div className="subscription-page-heading"><div><p className="eyebrow">SUBSCRIPTION</p><h2>Your plan and usage</h2></div></div>
    <div className="subscription-overview"><div className="subscription-card loading-card" /><div className="subscription-card loading-card" /></div>
  </section>;
}

function validateSubscription(value) {
  if (!isRecord(value)
    || !isPlanCode(value.current_plan)
    || !isNonEmptyString(value.plan_name)
    || !isNonNegativeNumber(value.price_lkr)
    || !isNonNegativeInteger(value.monthly_analysis_limit)
    || !SUBSCRIPTION_STATUSES.has(value.subscription_status)
    || !isValidDate(value.current_period_start)
    || !isValidDate(value.current_period_end)
    || new Date(value.current_period_end) <= new Date(value.current_period_start)) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
}

function validateUsage(value) {
  if (!isRecord(value)
    || !isPlanCode(value.plan)
    || !isNonNegativeInteger(value.used)
    || !isNonNegativeInteger(value.remaining)
    || !isNonNegativeInteger(value.monthly_analysis_limit)
    || !isValidDate(value.current_period_start)
    || !isValidDate(value.current_period_end)
    || new Date(value.current_period_end) <= new Date(value.current_period_start)
    || value.used > value.monthly_analysis_limit
    || value.remaining > value.monthly_analysis_limit
    || value.used + value.remaining !== value.monthly_analysis_limit) {
    throw new Error("The subscription usage service returned an invalid response. Please refresh and try again.");
  }
}

function validateSubscriptionUsageConsistency(subscription, usage) {
  if (subscription.current_plan !== usage.plan
    || subscription.monthly_analysis_limit !== usage.monthly_analysis_limit
    || subscription.current_period_start !== usage.current_period_start
    || subscription.current_period_end !== usage.current_period_end) {
    throw new Error("The subscription service returned inconsistent data. Please refresh and try again.");
  }
}

function validatePlanChangeResponse(value, requestedPlanCode) {
  if (!isRecord(value) || !isNonEmptyString(value.message) || !isRecord(value.subscription)) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
  validateSubscription(value.subscription);
  const scheduledPlan = value.scheduled_plan_code;
  if (scheduledPlan !== null && !isPlanCode(scheduledPlan)) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
  if (scheduledPlan && scheduledPlan !== requestedPlanCode) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
  if (!scheduledPlan && value.subscription.current_plan !== requestedPlanCode) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
  if (scheduledPlan && value.subscription.current_plan === requestedPlanCode) {
    throw new Error("The subscription service returned an invalid response. Please refresh and try again.");
  }
  return scheduledPlan;
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPlanCode(value) {
  return typeof value === "string" && PLAN_BY_CODE.has(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function isNonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isNonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function isValidDate(value) {
  return typeof value === "string" && !Number.isNaN(new Date(value).getTime());
}

function toDisplayError(error) {
  if (error instanceof ApiError && error.status === 404) return { title: "Subscription not found", message: "Your account does not have an active subscription yet. Please try again after your account is provisioned." };
  if (error instanceof ApiError && error.status === 429) return { title: "Request temporarily limited", message: "Please wait a moment and try again." };
  if (error instanceof ApiError && error.status === 0) return { title: "Unable to connect", message: error.message };
  return { title: "Subscription unavailable", message: error?.message || "Please try again shortly." };
}

function formatLkr(value) {
  return `LKR ${value.toLocaleString("en-LK", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

function formatDate(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-LK", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

function planLabel(code) {
  return PLAN_BY_CODE.get(code)?.name || code;
}
