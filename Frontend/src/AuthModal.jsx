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

export default function AuthModal({ isOpen, onClose, onAuthSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const googleButtonRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;

    let cancelled = false;
    async function initialiseGoogleSignIn() {
      try {
        const [clientId] = await Promise.all([getGoogleClientId(), loadGoogleIdentityServices()]);
        if (cancelled || !googleButtonRef.current) return;

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
          text: "continue_with",
          width: 272,
        });
      } catch (err) {
        if (!cancelled) setError(err.message || "Google sign-in is unavailable.");
      }
    }

    initialiseGoogleSignIn();
    return () => {
      cancelled = true;
    };
  }, [isOpen, onAuthSuccess, onClose]);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isRegister) {
        await registerUser(email, password);
        await loginUser(email, password);
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

  return (
    <div className="auth-overlay" role="presentation">
      <div className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button
          type="button"
          onClick={onClose}
          className="auth-close"
          aria-label="Close modal"
        >
          &times;
        </button>
        <div className="auth-brand"><span>F</span> FinAssist <b>AI</b></div>
        <p className="auth-kicker">{isRegister ? "GET STARTED" : "WELCOME BACK"}</p>
        <h3 id="auth-title">{isRegister ? "Create your account" : "Sign in to FinAssist"}</h3>
        <p className="auth-subtitle">
          {isRegister ? "Start exploring clearer financial decisions." : "Pick up where your financial research left off."}
        </p>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-field">
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? "Processing..." : isRegister ? "Sign Up" : "Log In"}
          </button>
        </form>
        <div className="auth-divider" aria-hidden="true">
          <span />
          <span>or</span>
          <span />
        </div>
        <div
          ref={googleButtonRef}
          style={{
            opacity: loading || googleLoading ? 0.65 : 1,
            pointerEvents: loading || googleLoading ? "none" : "auto",
          }}
          className="google-sign-in"
          aria-label="Continue with Google"
          aria-busy={googleLoading}
        >
          {googleLoading && "Signing in with Google..."}
        </div>
        <button
          type="button"
          onClick={() => {
            setIsRegister(!isRegister);
            setError("");
          }}
          className="auth-switch"
        >
          {isRegister
            ? "Already have an account? Log in"
            : "Need an account? Register"}
        </button>
      </div>
    </div>
  );
}
