import { useEffect, useState } from "react";
import { ApiError } from "./api";
import { getSubscription, getSubscriptionUsage, simulateSubscriptionChange } from "./subscriptionApi";

const PLANS = Object.freeze([
  {
    code: "free",
    name: "Free Starter",
    price: 0,
    limit: 5,
    description: "Great for trying out source-backed financial research.",
    features: [
      "5 AI Financial Analyses / month",
      "Source-grounded evidence search",
      "Financial risk breakdown",
      "Saved conversation history",
    ],
  },
  {
    code: "basic",
    name: "Basic Pro",
    price: 499,
    limit: 50,
    popular: true,
    description: "Ideal for regular financial research and learning.",
    features: [
      "50 AI Financial Analyses / month",
      "Source-grounded evidence search",
      "Detailed risk category analysis",
      "Faster AI response priority",
      "Saved conversation history",
    ],
  },
  {
    code: "premium",
    name: "Premium Unlimited",
    price: 999,
    limit: 200,
    description: "For high-volume financial research and power users.",
    features: [
      "200 AI Financial Analyses / month",
      "Priority AI processing queue",
      "Deep evidence & web search",
      "Comprehensive risk evaluation",
      "Unlimited saved chat history",
    ],
  },
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
      const [subscriptionData, usageData] = await Promise.all([
        getSubscription(),
        getSubscriptionUsage(),
      ]);
      validateSubscription(subscriptionData);
      validateUsage(usageData);
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

  useEffect(() => {
    refreshSubscription();
  }, []);

  async function changePlan(planCode) {
    if (!subscription || planCode === subscription.current_plan || isChanging) return;
    setIsChanging(true);
    setError(null);
    setNotice("");
    try {
      const result = await simulateSubscriptionChange(planCode);
      const scheduledPlan = validatePlanChangeResponse(result, planCode);
      setNotice(
        scheduledPlan
          ? `Your switch to ${planLabel(scheduledPlan)} has been scheduled for your next billing cycle.`
          : `Success! You are now subscribed to the ${planLabel(planCode)} plan.`
      );
      await refreshSubscription();
    } catch (requestError) {
      setError(toDisplayError(requestError));
    } finally {
      setIsChanging(false);
    }
  }

  if (isLoading) return <SubscriptionLoading />;

  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <div className="subscription-page-heading">
        <div>
          <p className="eyebrow">MY ACCOUNT</p>
          <h2 id="subscription-title">Subscription & Allowance</h2>
          <p>View your monthly AI analysis usage and select the best plan for your needs.</p>
        </div>
        <button className="subscription-refresh" type="button" onClick={refreshSubscription}>
          ↻ Refresh
        </button>
      </div>

      {quotaLimitReached && <QuotaLimitNotice onDismiss={onDismissQuotaLimit} />}
      {notice && <div className="subscription-notice" role="status">✓ {notice}</div>}
      {error && <SubscriptionError error={error} onRetry={refreshSubscription} />}

      {!error && subscription && usage && (
        <>
          <div className="subscription-overview">
            <CurrentSubscriptionCard subscription={subscription} usage={usage} />
          </div>

          <section className="pricing-section" aria-labelledby="plans-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">AVAILABLE PLANS</p>
                <h3 id="plans-title">Select Your Plan</h3>
              </div>
              <p>Choose an allowance that fits your financial research goals.</p>
            </div>

            <div className="plan-grid">
              {PLANS.map((plan) => (
                <PlanCard
                  key={plan.code}
                  plan={plan}
                  currentPlan={subscription.current_plan}
                  onChange={changePlan}
                  isChanging={isChanging}
                />
              ))}
            </div>
          </section>

          <p className="simulation-notice">
            ℹ️ Plan updates take effect immediately for your account.
          </p>
        </>
      )}
    </section>
  );
}

function CurrentSubscriptionCard({ subscription, usage }) {
  const percent =
    usage?.monthly_analysis_limit > 0
      ? Math.min(100, Math.round((usage.used / usage.monthly_analysis_limit) * 100))
      : 0;

  return (
    <section className="subscription-card current-subscription-card" aria-labelledby="current-plan-title">
      <div className="card-heading">
        <p className="eyebrow">ACTIVE PLAN</p>
        <span className="subscription-status">{subscription.subscription_status}</span>
      </div>

      <div className="sub-hero-row">
        <div>
          <h3 id="current-plan-title">{subscription.plan_name} Plan</h3>
          <p className="plan-price">
            {formatLkr(subscription.price_lkr)}
            <span> / month</span>
          </p>
        </div>
        <div className="usage-stat-box">
          <span className="usage-number">{usage ? usage.remaining : 0}</span>
          <span className="usage-label">Analyses Remaining</span>
        </div>
      </div>

      <div className="usage-bar-section">
        <div className="usage-bar-header">
          <span>Monthly Allowance Usage</span>
          <strong>
            {usage ? usage.used : 0} / {subscription.monthly_analysis_limit} used ({percent}%)
          </strong>
        </div>
        <div
          className="usage-progress"
          role="progressbar"
          aria-label="Monthly analysis usage"
          aria-valuemin="0"
          aria-valuemax={subscription.monthly_analysis_limit}
          aria-valuenow={usage ? usage.used : 0}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
      </div>

      <dl className="subscription-details">
        <div>
          <dt>Billing Period</dt>
          <dd>
            {formatDate(subscription.current_period_start)} – {formatDate(subscription.current_period_end)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function PlanCard({ plan, currentPlan, onChange, isChanging }) {
  const isCurrent = plan.code === currentPlan;
  const current = PLANS.find((item) => item.code === currentPlan);
  const isUpgrade = plan.price > (current?.price ?? 0);
  const label = isCurrent
    ? "Current Active Plan"
    : isUpgrade
    ? `Upgrade to ${plan.name}`
    : `Switch to ${plan.name}`;

  return (
    <article className={`plan-card ${isCurrent ? "current" : ""} ${plan.popular ? "popular" : ""}`}>
      {isCurrent && <span className="current-plan-badge">Active Plan</span>}
      {!isCurrent && plan.popular && <span className="popular-plan-badge">Most Popular</span>}

      <p className="plan-name">{plan.name}</p>
      <p className="plan-price">
        {formatLkr(plan.price)}
        <span>/month</span>
      </p>
      <p className="plan-allowance">⚡ {plan.limit} Analyses per month</p>
      <p className="plan-description">{plan.description}</p>

      <ul className="plan-features-list">
        {plan.features.map((feature, idx) => (
          <li key={idx}>{feature}</li>
        ))}
      </ul>

      <button
        className="plan-action"
        type="button"
        disabled={isCurrent || isChanging}
        onClick={() => onChange(plan.code)}
      >
        {isChanging && !isCurrent ? "Updating..." : label}
      </button>
    </article>
  );
}

function SubscriptionError({ error, onRetry }) {
  return (
    <div className="subscription-error" role="alert">
      <div>
        <strong>{error.title}</strong>
        <p>{error.message}</p>
      </div>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

function QuotaLimitNotice({ onDismiss }) {
  return (
    <div className="subscription-error quota-limit-notice" role="alert">
      <div>
        <strong>Monthly Limit Reached</strong>
        <p>
          You have used all available AI analyses for this billing period. Upgrade your plan below to continue researching immediately!
        </p>
      </div>
      <button type="button" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

function SubscriptionLoading() {
  return (
    <section className="subscription-page" aria-label="Loading subscription">
      <div className="subscription-page-heading">
        <div>
          <p className="eyebrow">SUBSCRIPTION</p>
          <h2>Your Plan and Usage</h2>
        </div>
      </div>
      <div className="subscription-overview">
        <div className="subscription-card loading-card" />
      </div>
    </section>
  );
}

function validateSubscription(value) {
  if (
    !isRecord(value) ||
    !isPlanCode(value.current_plan) ||
    !isNonEmptyString(value.plan_name) ||
    !isNonNegativeNumber(value.price_lkr) ||
    !isNonNegativeInteger(value.monthly_analysis_limit) ||
    !SUBSCRIPTION_STATUSES.has(value.subscription_status) ||
    !isValidDate(value.current_period_start) ||
    !isValidDate(value.current_period_end)
  ) {
    throw new Error("Unable to load subscription details. Please refresh and try again.");
  }
}

function validateUsage(value) {
  if (
    !isRecord(value) ||
    !isPlanCode(value.plan) ||
    !isNonNegativeInteger(value.used) ||
    !isNonNegativeInteger(value.remaining) ||
    !isNonNegativeInteger(value.monthly_analysis_limit) ||
    !isValidDate(value.current_period_start) ||
    !isValidDate(value.current_period_end)
  ) {
    throw new Error("Unable to load usage data. Please refresh and try again.");
  }
}

function validatePlanChangeResponse(value, requestedPlanCode) {
  if (!isRecord(value) || !isRecord(value.subscription)) {
    throw new Error("Unable to complete plan change. Please try again.");
  }
  return value.scheduled_plan_code;
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
  if (error instanceof ApiError && error.status === 404)
    return {
      title: "Subscription Setup Needed",
      message: "Your account subscription is being initialized. Please try again in a few moments.",
    };
  if (error instanceof ApiError && error.status === 429)
    return { title: "Request Limited", message: "Please wait a moment before trying again." };
  return {
    title: "Service Unavailable",
    message: error?.message || "Unable to connect to subscription services. Please try again shortly.",
  };
}

function formatLkr(value) {
  if (value === 0) return "Free";
  return `LKR ${value.toLocaleString("en-LK")}`;
}

function formatDate(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-LK", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

function planLabel(code) {
  return PLAN_BY_CODE.get(code)?.name || code;
}
