import { useEffect, useState } from "react";
import { ApiError } from "./api";
import {
  cancelSubscription,
  getPaymentMethods,
  getPublicPlans,
  getSubscription,
  getSubscriptionUsage,
  simulateSubscriptionChange,
} from "./subscriptionApi";

const PLANS = Object.freeze([
  {
    code: "free",
    name: "Free Starter",
    price: 0,
    limit: 5,
    description: "Great for exploring source-backed financial research and risk evaluation.",
    features: [
      "5 AI Financial Analyses / month",
      "Source-grounded evidence search",
      "Financial risk severity breakdown",
      "Key decision considerations",
      "Saved conversation history",
    ],
  },
  {
    code: "basic",
    name: "Basic Pro",
    price: 499,
    limit: 50,
    popular: true,
    description: "Ideal for regular financial research, investors, and continuous learning.",
    features: [
      "50 AI Financial Analyses / month",
      "Source-grounded evidence search",
      "Detailed risk category analysis",
      "Key decision-making checklists",
      "Faster AI response priority",
      "Saved conversation history",
    ],
  },
  {
    code: "premium",
    name: "Premium Unlimited",
    price: 999,
    limit: 200,
    description: "For high-volume financial research, institutions, and power analysts.",
    features: [
      "200 AI Financial Analyses / month",
      "Priority AI processing queue",
      "Deep regulatory & central bank search",
      "Comprehensive multi-tier risk evaluation",
      "Advanced decision support & follow-ups",
      "Unlimited saved chat history",
    ],
  },
]);

const PLAN_BY_CODE = new Map(PLANS.map((plan) => [plan.code, plan]));
const SUBSCRIPTION_STATUSES = new Set(["active", "cancelled", "expired"]);

export default function SubscriptionPage({
  quotaLimitReached = false,
  onDismissQuotaLimit,
  isLoggedIn = false,
  onOpenAuth,
}) {
  const [subscription, setSubscription] = useState(null);
  const [usage, setUsage] = useState(null);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [publicPlans, setPublicPlans] = useState(PLANS);
  const [isLoading, setIsLoading] = useState(true);
  const [isChanging, setIsChanging] = useState(false);
  const [selectedPlanForModal, setSelectedPlanForModal] = useState(null);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [showUsageHistory, setShowUsageHistory] = useState(false);

  async function refreshSubscription() {
    setIsLoading(true);
    setError(null);

    if (!isLoggedIn) {
      try {
        const publicList = await getPublicPlans();
        if (Array.isArray(publicList) && publicList.length > 0) {
          setPublicPlans(
            PLANS.map((p) => {
              const remote = publicList.find((r) => r.code === p.code);
              return remote ? { ...p, price: remote.price_lkr, limit: remote.monthly_analysis_limit } : p;
            })
          );
        }
      } catch {
        // Fallback to local constant
      }
      setSubscription(null);
      setUsage(null);
      setPaymentMethods([]);
      setIsLoading(false);
      return;
    }

    try {
      const [subscriptionData, usageData, paymentMethodsData] = await Promise.all([
        getSubscription(),
        getSubscriptionUsage(),
        getPaymentMethods().catch(() => []),
      ]);
      validateSubscription(subscriptionData);
      validateUsage(usageData);
      setSubscription(subscriptionData);
      setUsage(usageData);
      setPaymentMethods(Array.isArray(paymentMethodsData) ? paymentMethodsData : []);
    } catch (requestError) {
      if (requestError?.status === 401) {
        setSubscription(null);
        setUsage(null);
        setPaymentMethods([]);
      } else {
        setError(toDisplayError(requestError));
        setSubscription(null);
        setUsage(null);
        setPaymentMethods([]);
      }
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    refreshSubscription();
  }, [isLoggedIn]);

  function handlePlanClick(planCode) {
    if (!isLoggedIn) {
      if (onOpenAuth) onOpenAuth("register");
      return;
    }
    if (!subscription || planCode === subscription.current_plan || isChanging) return;
    const targetPlan = PLANS.find((p) => p.code === planCode);
    if (targetPlan) {
      setSelectedPlanForModal(targetPlan);
    }
  }

  async function confirmPlanChange(paymentSelection = {}) {
    if (!selectedPlanForModal || isChanging) return;
    const planCode = selectedPlanForModal.code;
    setIsChanging(true);
    setError(null);
    setNotice("");
    try {
      const result = await simulateSubscriptionChange(planCode, paymentSelection);
      const scheduledPlan = validatePlanChangeResponse(result, planCode);
      setNotice(
        scheduledPlan
          ? `Your switch to ${planLabel(scheduledPlan)} has been scheduled for your next billing cycle.`
          : `Success! You are now subscribed to the ${planLabel(planCode)} plan.`
      );
      setSelectedPlanForModal(null);
      await refreshSubscription();
    } catch (requestError) {
      setError(toDisplayError(requestError));
    } finally {
      setIsChanging(false);
    }
  }

  async function confirmCancelSubscription() {
    if (isCancelling) return;
    setIsCancelling(true);
    setError(null);
    setNotice("");
    try {
      const result = await cancelSubscription();
      setNotice(
        result.message || "Your subscription has been scheduled to cancel at the end of the billing period."
      );
      setShowCancelModal(false);
      await refreshSubscription();
    } catch (requestError) {
      setError(toDisplayError(requestError));
    } finally {
      setIsCancelling(false);
    }
  }

  if (isLoading) return <SubscriptionLoading />;

  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <div className="subscription-page-heading">
        <div>
          <p className="eyebrow">MY ACCOUNT</p>
          <h2 id="subscription-title">Subscription & Allowance</h2>
          <p>
            {isLoggedIn
              ? "View your monthly AI analysis usage and select the best plan for your financial research."
              : "Explore our plans and allowance tiers. Sign in or create an account to start researching."}
          </p>
        </div>
        {isLoggedIn && (
          <button className="subscription-refresh" type="button" onClick={refreshSubscription}>
            ↻ Refresh
          </button>
        )}
      </div>

      {!isLoggedIn && (
        <div className="guest-subscription-banner">
          <div>
            <strong>Sign in to manage your subscription</strong>
            <p>Create a free account to receive 5 free AI financial analyses every month.</p>
          </div>
          <button
            type="button"
            className="guest-auth-btn"
            onClick={() => onOpenAuth && onOpenAuth("register")}
          >
            Create Free Account
          </button>
        </div>
      )}

      {quotaLimitReached && <QuotaLimitNotice onDismiss={onDismissQuotaLimit} />}
      {notice && (
        <div className="subscription-notice" role="status">
          ✓ {notice}
        </div>
      )}
      {error && <SubscriptionError error={error} onRetry={refreshSubscription} />}

      {isLoggedIn && !error && subscription && usage && (
        <>
          {subscription.scheduled_plan_code && (
            <div className="scheduled-plan-alert" role="status">
              <span className="alert-icon">ℹ️</span>
              <div>
                <strong>Upcoming Plan Change</strong>
                <p>
                  Your plan is scheduled to switch to{" "}
                  <strong>{planLabel(subscription.scheduled_plan_code)}</strong> at the end of
                  your current billing cycle ({formatDate(subscription.current_period_end)}).
                </p>
              </div>
            </div>
          )}

          <div className="subscription-overview">
            <CurrentSubscriptionCard
              subscription={subscription}
              usage={usage}
              paymentMethods={paymentMethods}
              onCancelClick={() => setShowCancelModal(true)}
              onToggleHistory={() => setShowUsageHistory(!showUsageHistory)}
              showHistory={showUsageHistory}
            />
          </div>

          {showUsageHistory && (
            <UsageHistorySection usageEvents={usage.usage_events || []} />
          )}
        </>
      )}

      {/* Available Plans Grid */}
      <section className="pricing-section" aria-labelledby="plans-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">AVAILABLE PLANS</p>
            <h3 id="plans-title">Select Your Plan</h3>
          </div>
          <p>Choose an allowance that fits your financial research goals.</p>
        </div>

        <div className="plan-grid">
          {publicPlans.map((plan) => (
            <PlanCard
              key={plan.code}
              plan={plan}
              currentPlan={subscription?.current_plan}
              scheduledPlan={subscription?.scheduled_plan_code}
              isLoggedIn={isLoggedIn}
              onChange={handlePlanClick}
              isChanging={isChanging}
            />
          ))}
        </div>
      </section>

      <p className="simulation-notice">
        ℹ️ <strong>Academic Simulation</strong>: FinAssist operates with simulated billing in Sri Lankan Rupees (LKR). Plan upgrades activate additional analysis capacity immediately.
      </p>

      {/* Plan Change Confirmation Modal */}
      {selectedPlanForModal && (
        <PlanConfirmationModal
          targetPlan={selectedPlanForModal}
          currentPlanCode={subscription?.current_plan}
          currentPlanObj={subscription ? PLANS.find((p) => p.code === subscription.current_plan) : null}
          paymentMethods={paymentMethods}
          isChanging={isChanging}
          onConfirm={confirmPlanChange}
          onClose={() => setSelectedPlanForModal(null)}
        />
      )}

      {/* Cancel Subscription Modal */}
      {showCancelModal && (
        <CancelConfirmationModal
          subscription={subscription}
          isCancelling={isCancelling}
          onConfirm={confirmCancelSubscription}
          onClose={() => setShowCancelModal(false)}
        />
      )}
    </section>
  );
}

function CurrentSubscriptionCard({
  subscription,
  usage,
  paymentMethods = [],
  onCancelClick,
  onToggleHistory,
  showHistory,
}) {
  const percent =
    usage?.monthly_analysis_limit > 0
      ? Math.min(100, Math.round((usage.used / usage.monthly_analysis_limit) * 100))
      : 0;

  const isPaid = subscription.current_plan !== "free";
  const defaultPayment = paymentMethods.find((pm) => pm.is_default) || paymentMethods[0];

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

      <div className="card-footer-details">
        <dl className="subscription-details">
          <div>
            <dt>Billing Period</dt>
            <dd>
              {formatDate(subscription.current_period_start)} – {formatDate(subscription.current_period_end)}
            </dd>
          </div>
          {defaultPayment && (
            <div>
              <dt>Payment Method</dt>
              <dd className="card-payment-inline">
                <span className={`brand-pill ${defaultPayment.brand.toLowerCase()}`}>
                  {defaultPayment.brand.toUpperCase()}
                </span>
                <span>•••• {defaultPayment.last4} (Exp {String(defaultPayment.exp_month).padStart(2, "0")}/{String(defaultPayment.exp_year).slice(-2)})</span>
              </dd>
            </div>
          )}
        </dl>

        <div className="card-action-links">
          <button
            type="button"
            className="secondary-link-btn"
            onClick={onToggleHistory}
          >
            {showHistory ? "Hide Activity History" : "View Activity History"}
          </button>

          {isPaid && !subscription.scheduled_plan_code && (
            <button
              type="button"
              className="danger-link-btn"
              onClick={onCancelClick}
            >
              Cancel Subscription
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function UsageHistorySection({ usageEvents }) {
  return (
    <div className="usage-history-card">
      <div className="usage-history-header">
        <h4>Recent Analysis Activity</h4>
        <span className="history-count-badge">
          {usageEvents.length} event{usageEvents.length === 1 ? "" : "s"}
        </span>
      </div>

      {usageEvents.length === 0 ? (
        <p className="empty-history-text">No analyses performed yet in this billing cycle.</p>
      ) : (
        <div className="history-table-wrapper">
          <table className="history-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Status</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {usageEvents.slice(-10).reverse().map((event) => (
                <tr key={event.id}>
                  <td className="event-id-cell">
                    <code>{event.id.slice(0, 8)}...</code>
                  </td>
                  <td>
                    <span className={`event-status-pill ${event.status}`}>
                      {event.status}
                    </span>
                  </td>
                  <td className="timestamp-cell">
                    {formatDateTime(event.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PlanCard({
  plan,
  currentPlan,
  scheduledPlan,
  isLoggedIn,
  onChange,
  isChanging,
}) {
  const isCurrent = isLoggedIn && plan.code === currentPlan;
  const isScheduled = isLoggedIn && plan.code === scheduledPlan;
  const current = PLANS.find((item) => item.code === currentPlan);
  const isUpgrade = plan.price > (current?.price ?? 0);

  let label = "Choose Plan";
  if (!isLoggedIn) {
    label = plan.price === 0 ? "Get Started Free" : `Select ${plan.name}`;
  } else if (isCurrent) {
    label = "Current Active Plan";
  } else if (isScheduled) {
    label = "Scheduled for Next Cycle";
  } else if (isUpgrade) {
    label = `Upgrade to ${plan.name}`;
  } else {
    label = `Switch to ${plan.name}`;
  }

  return (
    <article
      className={`plan-card ${isCurrent ? "current" : ""} ${plan.popular ? "popular" : ""}`}
    >
      {isCurrent && <span className="current-plan-badge">Active Plan</span>}
      {isScheduled && <span className="scheduled-badge">Scheduled</span>}
      {!isCurrent && !isScheduled && plan.popular && (
        <span className="popular-plan-badge">Most Popular</span>
      )}

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
        disabled={isCurrent || isScheduled || isChanging}
        onClick={() => onChange(plan.code)}
      >
        {isChanging && !isCurrent ? "Updating..." : label}
      </button>
    </article>
  );
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-LK", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function detectCardBrandFrontend(number) {
  const digits = (number || "").replace(/\D/g, "");
  if (!digits) return "generic";
  if (digits.startsWith("4")) return "visa";
  const first2 = parseInt(digits.slice(0, 2), 10);
  const first4 = parseInt(digits.slice(0, 4), 10);
  if ((first2 >= 51 && first2 <= 55) || (first4 >= 2221 && first4 <= 2720)) return "mastercard";
  if (digits.startsWith("34") || digits.startsWith("37")) return "amex";
  if (digits.startsWith("6011") || digits.startsWith("65")) return "discover";
  return "generic";
}

function formatCardNumberDisplay(value) {
  const digits = (value || "").replace(/\D/g, "").slice(0, 19);
  return digits.replace(/(\d{4})(?=\d)/g, "$1 ");
}

function formatExpiryDisplay(value) {
  const digits = (value || "").replace(/\D/g, "").slice(0, 4);
  if (digits.length >= 3) {
    return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  }
  return digits;
}

function PlanConfirmationModal({
  targetPlan,
  currentPlanCode,
  currentPlanObj,
  paymentMethods = [],
  isChanging,
  onConfirm,
  onClose,
}) {
  const isUpgrade = targetPlan.price > (currentPlanObj?.price ?? 0);
  const isPaidPlan = targetPlan.price > 0;

  const defaultMethod = paymentMethods.find((pm) => pm.is_default) || paymentMethods[0];
  const [paymentMode, setPaymentMode] = useState(
    paymentMethods.length > 0 ? "saved" : "new"
  );
  const [selectedMethodId, setSelectedMethodId] = useState(
    defaultMethod ? defaultMethod.id : ""
  );

  // New card fields
  const [cardHolderName, setCardHolderName] = useState("");
  const [cardNumber, setCardNumber] = useState("");
  const [cardExpiry, setCardExpiry] = useState("");
  const [cardCvv, setCardCvv] = useState("");
  const [saveCard, setSaveCard] = useState(true);
  const [validationError, setValidationError] = useState("");

  const brand = detectCardBrandFrontend(cardNumber);

  function handleCardNumberChange(e) {
    const formatted = formatCardNumberDisplay(e.target.value);
    setCardNumber(formatted);
    if (validationError) setValidationError("");
  }

  function handleExpiryChange(e) {
    const formatted = formatExpiryDisplay(e.target.value);
    setCardExpiry(formatted);
    if (validationError) setValidationError("");
  }

  function handleCvvChange(e) {
    const digits = e.target.value.replace(/\D/g, "").slice(0, brand === "amex" ? 4 : 3);
    setCardCvv(digits);
    if (validationError) setValidationError("");
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    if (!isPaidPlan) {
      onConfirm({});
      return;
    }

    if (paymentMode === "saved") {
      if (!selectedMethodId) {
        setValidationError("Please select a payment card to proceed.");
        return;
      }
      onConfirm({ paymentMethodId: selectedMethodId });
      return;
    }

    // Validate new card details
    const cleanName = cardHolderName.trim();
    if (!cleanName || cleanName.length < 2) {
      setValidationError("Please enter the cardholder's full name.");
      return;
    }

    const digits = cardNumber.replace(/\D/g, "");
    if (digits.length < 13 || digits.length > 19) {
      setValidationError("Please enter a valid card number (13-19 digits).");
      return;
    }

    const [monthStr, yearStr] = cardExpiry.split("/");
    const expMonth = parseInt(monthStr, 10);
    let expYear = parseInt(yearStr, 10);
    if (!expMonth || expMonth < 1 || expMonth > 12 || !expYear) {
      setValidationError("Please enter a valid expiration date in MM/YY format.");
      return;
    }
    if (expYear < 100) expYear += 2000;

    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    if (expYear < currentYear || (expYear === currentYear && expMonth < currentMonth)) {
      setValidationError("This card has expired. Please enter an active card.");
      return;
    }

    const cleanCvv = cardCvv.replace(/\D/g, "");
    const minCvv = brand === "amex" ? 4 : 3;
    if (cleanCvv.length < minCvv) {
      setValidationError(
        brand === "amex"
          ? "American Express cards require a 4-digit CVV code."
          : "Please enter a valid 3-digit CVV code."
      );
      return;
    }

    setValidationError("");
    onConfirm({
      cardDetails: {
        card_holder_name: cleanName,
        card_number: digits,
        exp_month: expMonth,
        exp_year: expYear,
        cvv: cleanCvv,
        save_card: saveCard,
      },
    });
  }

  return (
    <div className="auth-overlay" role="presentation" onClick={onClose}>
      <div
        className="auth-modal plan-confirm-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="auth-close"
          aria-label="Close modal"
        >
          &times;
        </button>

        <div className="auth-brand">
          <span className="brand-mark">F</span>
          <span>FinAssist <b>AI</b></span>
        </div>

        <h3>{isUpgrade ? "Confirm Plan Upgrade" : "Confirm Plan Change"}</h3>
        <p className="auth-subtitle">
          {isUpgrade
            ? `Upgrade from ${currentPlanObj?.name || "current plan"} to ${targetPlan.name}.`
            : `Schedule switch to ${targetPlan.name} for your next billing cycle.`}
        </p>

        <div className="modal-plan-summary">
          <div className="summary-row">
            <span>Selected Plan:</span>
            <strong>{targetPlan.name}</strong>
          </div>
          <div className="summary-row">
            <span>Monthly Price:</span>
            <strong>{formatLkr(targetPlan.price)} / month</strong>
          </div>
          <div className="summary-row">
            <span>Monthly Allowance:</span>
            <strong>⚡ {targetPlan.limit} AI Analyses</strong>
          </div>
          <div className="summary-row">
            <span>Effective Date:</span>
            <strong>{isUpgrade ? "Immediately" : "Next Billing Cycle"}</strong>
          </div>
        </div>

        {isPaidPlan && (
          <form className="payment-selection-form" onSubmit={handleFormSubmit}>
            <div className="payment-section-heading">
              <strong>Select Payment Method</strong>
              <p>Choose a payment card for your subscription renewal.</p>
            </div>

            {paymentMethods.length > 0 && (
              <div className="saved-methods-list" role="radiogroup" aria-label="Saved payment methods">
                {paymentMethods.map((pm) => (
                  <label
                    key={pm.id}
                    className={`payment-option-card ${paymentMode === "saved" && selectedMethodId === pm.id ? "selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="payment_option"
                      checked={paymentMode === "saved" && selectedMethodId === pm.id}
                      onChange={() => {
                        setPaymentMode("saved");
                        setSelectedMethodId(pm.id);
                        setValidationError("");
                      }}
                    />
                    <div className="payment-option-details">
                      <span className={`brand-pill ${pm.brand.toLowerCase()}`}>
                        {pm.brand.toUpperCase()}
                      </span>
                      <span className="card-number-text">•••• {pm.last4}</span>
                      <span className="card-exp-text">
                        Exp {String(pm.exp_month).padStart(2, "0")}/{String(pm.exp_year).slice(-2)}
                      </span>
                      {pm.is_default && <span className="default-pill">Default</span>}
                    </div>
                  </label>
                ))}

                <label
                  className={`payment-option-card ${paymentMode === "new" ? "selected" : ""}`}
                >
                  <input
                    type="radio"
                    name="payment_option"
                    checked={paymentMode === "new"}
                    onChange={() => {
                      setPaymentMode("new");
                      setValidationError("");
                    }}
                  />
                  <div className="payment-option-details">
                    <span className="new-card-icon">💳</span>
                    <strong className="new-card-title">Pay with a new card</strong>
                  </div>
                </label>
              </div>
            )}

            {paymentMode === "new" && (
              <div className="new-card-fields">
                <div className="auth-field">
                  <label htmlFor="modal-cardholder-name">Cardholder Name</label>
                  <input
                    id="modal-cardholder-name"
                    type="text"
                    value={cardHolderName}
                    onChange={(e) => {
                      setCardHolderName(e.target.value);
                      if (validationError) setValidationError("");
                    }}
                    placeholder="e.g. Ruwan Perera"
                    required
                  />
                </div>

                <div className="auth-field">
                  <label htmlFor="modal-card-number">
                    <span>Card Number</span>
                    {brand !== "generic" && (
                      <span className={`brand-pill ${brand}`}>
                        {brand.toUpperCase()}
                      </span>
                    )}
                  </label>
                  <div className="card-input-wrapper">
                    <input
                      id="modal-card-number"
                      type="text"
                      inputMode="numeric"
                      value={cardNumber}
                      onChange={handleCardNumberChange}
                      placeholder="4242 4242 4242 4242"
                      maxLength={19}
                      required
                    />
                  </div>
                </div>

                <div className="auth-name-row">
                  <div className="auth-field">
                    <label htmlFor="modal-card-expiry">Expires (MM/YY)</label>
                    <input
                      id="modal-card-expiry"
                      type="text"
                      inputMode="numeric"
                      value={cardExpiry}
                      onChange={handleExpiryChange}
                      placeholder="MM / YY"
                      maxLength={5}
                      required
                    />
                  </div>
                  <div className="auth-field">
                    <label htmlFor="modal-card-cvv">CVV / CVC</label>
                    <input
                      id="modal-card-cvv"
                      type="password"
                      inputMode="numeric"
                      value={cardCvv}
                      onChange={handleCvvChange}
                      placeholder={brand === "amex" ? "••••" : "•••"}
                      maxLength={brand === "amex" ? 4 : 3}
                      required
                    />
                  </div>
                </div>

                <label className="save-card-checkbox">
                  <input
                    type="checkbox"
                    checked={saveCard}
                    onChange={(e) => setSaveCard(e.target.checked)}
                  />
                  <span>Save this card for future renewals</span>
                </label>
              </div>
            )}

            {validationError && (
              <div className="auth-error-banner" role="alert">
                ⚠️ {validationError}
              </div>
            )}

            <div className="simulation-modal-notice">
              ℹ️ <strong>Simulated Billing</strong>: FinAssist validates card format in test mode. No actual charge will be debited to your card.
            </div>

            <div className="modal-btn-row">
              <button
                type="button"
                className="secondary-action"
                onClick={onClose}
                disabled={isChanging}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="auth-submit-btn"
                disabled={isChanging}
              >
                {isChanging ? "Processing..." : isUpgrade ? `Upgrade for ${formatLkr(targetPlan.price)}` : `Confirm Switch`}
              </button>
            </div>
          </form>
        )}

        {!isPaidPlan && (
          <>
            <div className="simulation-modal-notice">
              ℹ️ Switching to the Free Starter plan will reduce your monthly analysis allowance to 5 analyses at the start of your next billing cycle.
            </div>
            <div className="modal-btn-row">
              <button
                type="button"
                className="secondary-action"
                onClick={onClose}
                disabled={isChanging}
              >
                Cancel
              </button>
              <button
                type="button"
                className="auth-submit-btn"
                onClick={() => onConfirm({})}
                disabled={isChanging}
              >
                {isChanging ? "Processing..." : "Confirm Free Starter Plan"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CancelConfirmationModal({
  subscription,
  isCancelling,
  onConfirm,
  onClose,
}) {
  return (
    <div className="auth-overlay" role="presentation" onClick={onClose}>
      <div
        className="auth-modal plan-confirm-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="auth-close"
          aria-label="Close modal"
        >
          &times;
        </button>

        <h3>Cancel Subscription</h3>
        <p className="auth-subtitle">
          Are you sure you want to cancel your {subscription?.plan_name} subscription?
        </p>

        <div className="cancel-notice-box">
          <p>
            You will continue to have access to your {subscription?.monthly_analysis_limit} monthly analyses until{" "}
            <strong>{formatDate(subscription?.current_period_end)}</strong>. After that, your account will switch to the Free Starter plan (5 analyses/month).
          </p>
        </div>

        <div className="modal-btn-row">
          <button
            type="button"
            className="secondary-action"
            onClick={onClose}
            disabled={isCancelling}
          >
            Keep My Plan
          </button>
          <button
            type="button"
            className="danger-submit-btn"
            onClick={onConfirm}
            disabled={isCancelling}
          >
            {isCancelling ? "Cancelling..." : "Confirm Cancellation"}
          </button>
        </div>
      </div>
    </div>
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
