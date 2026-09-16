import { useState } from "react";
import { loginUser, registerUser } from "./authApi";

export default function AuthModal({ isOpen, onClose, onAuthSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <h3>{isRegister ? "Create Account" : "Log In"}</h3>
        {error && <p style={{ color: "red", fontSize: "14px" }}>{error}</p>}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "12px" }}>
            <label style={{ display: "block", marginBottom: "4px" }}>
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", marginBottom: "4px" }}>
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
            />
          </div>
          <button type="submit" disabled={loading} style={buttonStyle}>
            {loading ? "Processing..." : isRegister ? "Sign Up" : "Log In"}
          </button>
        </form>
        <button
          onClick={() => {
            setIsRegister(!isRegister);
            setError("");
          }}
          style={{
            background: "none",
            border: "none",
            color: "#4f46e5",
            marginTop: "12px",
            cursor: "pointer",
          }}
        >
          {isRegister
            ? "Already have an account? Log in"
            : "Need an account? Register"}
        </button>
      </div>
    </div>
  );
}

const overlayStyle = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};
const modalStyle = {
  background: "#fff",
  padding: "24px",
  borderRadius: "8px",
  width: "320px",
  color: "#333",
};
const inputStyle = {
  width: "100%",
  padding: "8px",
  borderRadius: "4px",
  border: "1px solid #ccc",
  boxSizing: "border-box",
};
const buttonStyle = {
  width: "100%",
  padding: "10px",
  background: "#4f46e5",
  color: "#fff",
  border: "none",
  borderRadius: "4px",
  cursor: "pointer",
};