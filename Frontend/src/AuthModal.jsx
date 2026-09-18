import { useEffect, useRef, useState } from "react";
import { getGoogleClientId, loginUser, loginWithGoogle, registerUser } from "./authApi";

const GOOGLE_IDENTITY_SCRIPT = "https://accounts.google.com/gsi/client";

function loadGoogleIdentityServices() {
  if (window.google?.accounts?.id) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const existingScript = document.querySelector(`script[src="${GOOGLE_IDENTITY_SCRIPT}"]`);
    if (existingScript) {
      existingScript.addEventListener("load", resolve, { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Google Sign-In could not be loaded.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = GOOGLE_IDENTITY_SCRIPT;
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Google Sign-In could not be loaded."));
    document.head.appendChild(script);
  });
}

function GoogleIcon() {
  return (
    <svg className="google-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
      />
    </svg>
  );
}

export default function AuthModal({ isOpen, onClose, onAuthSuccess, initialMode = "login" }) {
  const [isRegister, setIsRegister] = useState(initialMode === "register");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const googleButtonRef = useRef(null);

  useEffect(() => {
    setIsRegister(initialMode === "register");
  }, [initialMode, isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;

    let cancelled = false;
    async function initialiseGoogleSignIn() {
      try {
        const [clientId] = await Promise.all([getGoogleClientId(), loadGoogleIdentityServices()]);
        if (cancelled) return;
        if (!clientId) {
          setGoogleConfigured(false);
          return;
        }

        setGoogleConfigured(true);
        if (!googleButtonRef.current) return;

        window.google.accounts.id.initialize({
          client_id: clientId,
          auto_select: false,
          cancel_on_tap_outside: true,
          callback: async ({ credential }) => {
            if (!credential) {
              setError("Google sign-in was cancelled.");
              return;
            }
            setError("");
            setGoogleLoading(true);
            try {
              await loginWithGoogle(credential);
              onAuthSuccess();
              onClose();
            } catch (err) {
              setError(err.message || "Google sign-in failed. Please try again.");
            } finally {
              setGoogleLoading(false);
            }
          },
        });
        googleButtonRef.current.replaceChildren();
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: isRegister ? "signup_with" : "signin_with",
          width: 320,
          shape: "rectangular",
          logo_alignment: "left",
        });
      } catch (err) {
        if (!cancelled) setGoogleConfigured(false);
      }
    }

    initialiseGoogleSignIn();
    return () => {
      cancelled = true;
    };
  }, [isOpen, isRegister, onAuthSuccess, onClose]);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isRegister) {
        if (!firstName.trim() || !lastName.trim()) {
          setError("Please enter your first and last name.");
          setLoading(false);
          return;
        }
        await registerUser(firstName, lastName, email, password);
      } else {
        await loginUser(email, password);
      }
      onAuthSuccess();
      onClose();
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleGoogleCustomClick() {
    if (window.google?.accounts?.id && googleConfigured) {
      window.google.accounts.id.prompt((notification) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          setError("Please click the Google button directly to complete sign-in.");
        }
      });
    } else {
      setError("Google Sign-In is not configured. Set GOOGLE_CLIENT_ID in .env or use email login.");
    }
  }

  return (
    <div className="auth-overlay" role="presentation" onClick={onClose}>
      <div
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
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

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            className={`auth-tab ${!isRegister ? "active" : ""}`}
            onClick={() => {
              setIsRegister(false);
              setError("");
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            className={`auth-tab ${isRegister ? "active" : ""}`}
            onClick={() => {
              setIsRegister(true);
              setError("");
            }}
          >
            Create Account
          </button>
        </div>

        <h3 id="auth-title">
          {isRegister ? "Create your FinAssist account" : "Sign in to your account"}
        </h3>
        <p className="auth-subtitle">
          {isRegister
            ? "Register to access source-backed financial intelligence and risk analysis."
            : "Continue your research with persistent conversation history."}
        </p>

        {error && (
          <div className="auth-error-banner" role="alert">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Google OAuth Section with prominent Google icon */}
        <div className="auth-google-wrapper">
          <div
            ref={googleButtonRef}
            className="google-gis-container"
            style={{ display: googleConfigured ? "block" : "none" }}
          />
          {!googleConfigured && (
            <button
              type="button"
              className="google-auth-button"
              onClick={handleGoogleCustomClick}
              disabled={loading || googleLoading}
              aria-label={isRegister ? "Sign up with Google" : "Sign in with Google"}
            >
              <GoogleIcon />
              <span>{isRegister ? "Sign up with Google" : "Sign in with Google"}</span>
            </button>
          )}
        </div>

        <div className="auth-divider" aria-hidden="true">
          <span />
          <span>or continue with email</span>
          <span />
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {isRegister && (
            <div className="auth-name-row">
              <div className="auth-field">
                <label htmlFor="auth-first-name">First name</label>
                <input
                  id="auth-first-name"
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="e.g. Alex"
                  autoComplete="given-name"
                />
              </div>
              <div className="auth-field">
                <label htmlFor="auth-last-name">Last name</label>
                <input
                  id="auth-last-name"
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="e.g. Silva"
                  autoComplete="family-name"
                />
              </div>
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isRegister ? "At least 6 characters" : "Enter your password"}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </div>

          <button className="auth-submit-btn" type="submit" disabled={loading || googleLoading}>
            {loading ? (
              <span className="auth-spinner-label">
                <span className="loading-dot" /> Processing...
              </span>
            ) : isRegister ? (
              "Create Account"
            ) : (
              "Sign In"
            )}
          </button>
        </form>

        <p className="auth-footer-prompt">
          {isRegister ? "Already have an account? " : "Don't have an account? "}
          <button
            type="button"
            className="auth-link-button"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
            }}
          >
            {isRegister ? "Sign In" : "Sign Up"}
          </button>
        </p>
      </div>
    </div>
  );
}
