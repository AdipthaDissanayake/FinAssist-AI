import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ApiError, api } from "./api";
import SubscriptionPage from "./SubscriptionPage";

import AuthModal from "./AuthModal";
import { getProfile, logoutUser } from "./authApi";
import "./styles.css";

const suggestions = [
  {
    label: "Loan repayment risks",
    question: "What are the risks of taking a loan?",
  },
  {
    label: "Investment concentration risk",
    question: "What is concentration risk in investing?",
  },
  {
    label: "Fixed deposit considerations",
    question: "What should I know before putting money into a fixed deposit?",
  },
  {
    label: "Financial risks of betting",
    question: "What are the financial risks associated with betting?",
  },
];

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("finassist-theme") || "dark",
  );
  const [activeView, setActiveView] = useState(currentViewFromHash);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [quotaLimitReached, setQuotaLimitReached] = useState(false);
  const inputRef = useRef(null);
  const messageEndRef = useRef(null);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [isLoggedIn, setIsLoggedIn] = useState(() =>
    Boolean(localStorage.getItem("token")),
  );
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("finassist-theme", theme);
  }, [theme]);
  useEffect(() => {
    loadChats();
  }, [isLoggedIn]);
  useEffect(() => {
    let disposed = false;
    if (!isLoggedIn) {
      setCurrentUser(null);
      return undefined;
    }

    getProfile()
      .then((profile) => {
        if (!disposed) setCurrentUser(profile);
      })
      .catch(() => {
        if (!disposed) {
          logoutUser();
          setIsLoggedIn(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [isLoggedIn]);
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);
  useEffect(() => {
    const updateView = () => setActiveView(currentViewFromHash());
    window.addEventListener("hashchange", updateView);
    return () => window.removeEventListener("hashchange", updateView);
  }, []);

  async function loadChats() {
    if (!isLoggedIn) {
      setChats([]);
      return;
    }
    try {
      setChats(await api("/api/chats"));
    } catch (requestError) {
      if (requestError?.status === 401) {
        handleLogout();
      } else {
        setError(requestError.message);
      }
    }
  }
  async function openChat(chatId) {
    try {
      setError("");
      const data = await api(`/api/chats/${chatId}/messages`);
      setActiveChatId(chatId);
      setMessages(data.messages);
    } catch (requestError) {
      if (requestError?.status === 401) {
        handleLogout();
        setIsAuthOpen(true);
      } else {
        setError(requestError.message);
      }
    }
  }
  async function deleteChat(chatId) {
    try {
      setError("");
      await api(`/api/chats/${chatId}`, { method: "DELETE" });
      if (activeChatId === chatId) {
        setActiveChatId(null);
        setMessages([]);
      }
      await loadChats();
    } catch (requestError) {
      if (requestError?.status === 401) {
        handleLogout();
        setIsAuthOpen(true);
      } else {
        setError(requestError.message);
      }
    }
  }
  function handleLogout() {
    logoutUser();
    setIsLoggedIn(false);
    setCurrentUser(null);
    setChats([]);
    setMessages([]);
    setActiveChatId(null);
  }
  function startNewChat() {
    navigateTo("chat");
    setActiveChatId(null);
    setMessages([]);
    setError("");
    inputRef.current?.focus();
  }
  function useSuggestion(question) {
    setDraft(question);
    inputRef.current?.focus();
  }
  function navigateTo(view) {
    const hash =
      view === "subscription"
        ? "#/subscription"
        : view === "risk-evaluation"
          ? "#/risk-evaluation"
          : "#/";
    if (window.location.hash === hash) setActiveView(view);
    else window.location.hash = hash;
  }
  async function sendQuestion(question = draft) {
    const content = question.trim();
    if (!content || isSending) return;
    if (!isLoggedIn) {
      setAuthMode("login");
      setIsAuthOpen(true);
      setError("Please sign in or create an account to start financial research.");
      return;
    }
    setIsSending(true);
    setError("");
    try {
      let chatId = activeChatId;
      if (!chatId) {
        const chat = await api("/api/chats", {
          method: "POST",
          body: JSON.stringify({}),
        });
        chatId = chat.id;
        setActiveChatId(chatId);
      }
      const result = await api(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content, top_k: 3 }),
      });
      setMessages((current) => [
        ...current,
        result.user_message,
        result.assistant_message,
      ]);
      setDraft("");
      await loadChats();
    } catch (requestError) {
      if (
        requestError instanceof ApiError &&
        requestError.status === 429 &&
        requestError.payload?.error === "subscription_limit_reached"
      ) {
        setQuotaLimitReached(true);
        navigateTo("subscription");
      } else {
        setError(requestError.message);
      }
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Conversation history">
        <button
          className="brand"
          type="button"
          onClick={startNewChat}
          aria-label="Start a new chat"
        >
          <span className="brand-mark">F</span>
          <span>
            FinAssist <b>AI</b>
          </span>
        </button>

        <button
          className="new-chat-button"
          type="button"
          onClick={startNewChat}
        >
          <Icon name="plus" /> New chat
        </button>

        <button
          className={`sidebar-nav-button ${activeView === "subscription" ? "active" : ""}`}
          type="button"
          onClick={() => navigateTo("subscription")}
        >
          <Icon name="card" /> Subscription
        </button>

        <p className="sidebar-heading">Conversations</p>

        <nav className="chat-list" aria-label="Saved conversations">
          {chats.length === 0 && (
            <p className="empty-state">
              Your saved research will appear here.
            </p>
          )}

          {chats.map((chat) => (
            <div
              className={`chat-item-row ${activeView === "chat" && chat.id === activeChatId ? "active" : ""}`}
              key={chat.id}
            >
              <button
                className="chat-item"
                type="button"
                onClick={() => {
                  navigateTo("chat");
                  openChat(chat.id);
                }}
              >
                <span className="chat-item-title">{chat.title}</span>
                <span className="chat-item-preview">
                  {chat.preview || "No messages yet"}
                </span>
              </button>

              <button
                className="chat-delete-button"
                type="button"
                title="Delete conversation"
                aria-label={`Delete ${chat.title}`}
                onClick={(e) => {
                  e.stopPropagation();
                  deleteChat(chat.id);
                }}
              >
                <Icon name="trash" />
              </button>
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          {isLoggedIn ? (
            <div className="sidebar-user-badge">
              <span className="status-dot online" />
              <span className="sidebar-user-label">
                {currentUser?.first_name
                  ? `${currentUser.first_name} ${currentUser.last_name || ""}`.trim()
                  : currentUser?.email || "Signed In"}
              </span>
            </div>
          ) : (
            <button
              type="button"
              className="sidebar-signin-link"
              onClick={() => {
                setAuthMode("login");
                setIsAuthOpen(true);
              }}
            >
              <span className="status-dot" /> Sign in to save chats
            </button>
          )}
        </div>
      </aside>

      <section className="conversation-panel">
        <header className="topbar">
          <div>
            <h1>FinAssist AI</h1>
            <p>
              {activeView === "subscription"
                ? "Subscription and monthly usage"
                : "Source-backed financial research"}
            </p>
          </div>

          <div className="top-actions">
            {isLoggedIn ? (
              <div className="account-actions">
                <span
                  className="current-user"
                  title={
                    currentUser?.first_name
                      ? `${currentUser.first_name} ${currentUser.last_name || ""} (${currentUser.email})`
                      : currentUser?.email || "Account"
                  }
                >
                  <span className="current-user-avatar" aria-hidden="true">
                    {(currentUser?.first_name
                      ? currentUser.first_name.slice(0, 1)
                      : (currentUser?.email || "U").slice(0, 1)
                    ).toUpperCase()}
                  </span>
                  <span className="current-user-email">
                    {currentUser?.first_name
                      ? `${currentUser.first_name} ${currentUser.last_name || ""}`.trim()
                      : currentUser?.email || "User"}
                  </span>
                </span>
                <button className="theme-toggle" type="button" onClick={handleLogout}>
                  Log Out
                </button>
              </div>
            ) : (
              <div className="auth-nav-buttons">
                <button
                  className="theme-toggle"
                  type="button"
                  onClick={() => {
                    setAuthMode("login");
                    setIsAuthOpen(true);
                  }}
                >
                  Sign In
                </button>
                <button
                  className="theme-toggle register-nav-btn"
                  type="button"
                  onClick={() => {
                    setAuthMode("register");
                    setIsAuthOpen(true);
                  }}
                >
                  Sign Up
                </button>
              </div>
            )}

            <span className="source-status">
              <span className="status-dot" /> Trusted sources
            </span>

            <button
              className="theme-toggle"
              type="button"
              onClick={() =>
                setTheme(theme === "dark" ? "light" : "dark")
              }
              aria-label="Toggle colour theme"
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} />{" "}
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </div>
        </header>

        {activeView === "subscription" ? (
          <SubscriptionPage
            quotaLimitReached={quotaLimitReached}
            onDismissQuotaLimit={() => setQuotaLimitReached(false)}
          />
        ) : (
          <>
            <section className="message-view" aria-live="polite">
              {error && (
                <div className="error-notice" role="alert">
                  <Icon name="warning" />
                  {error}
                </div>
              )}

              {messages.length === 0 ? (
                <Welcome onSuggestion={useSuggestion} inputRef={inputRef} />
              ) : (
                messages.map((message) => (
                  <MessageCard
                    key={message.id}
                    message={message}
                    onSuggestion={useSuggestion}
                  />
                ))
              )}

              {isSending && (
                <div className="retrieving" role="status">
                  <span className="loading-dot" />
                  FinAssist is retrieving trusted evidence and evaluating financial risks...
                </div>
              )}

              <div ref={messageEndRef} />
            </section>

            <div className="composer-area">
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendQuestion();
                }}
              >
                <textarea
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendQuestion();
                    }
                  }}
                  placeholder="Ask any financial question (e.g. loan risks, fixed deposits, risk management)..."
                  rows={1}
                />
                <button
                  className="send-button"
                  type="submit"
                  disabled={!draft.trim() || isSending}
                  aria-label="Send financial question"
                >
                  <Icon name="send" />
                </button>
              </form>

              <p className="disclaimer">
                Educational information only — not personalised financial,
                investment, legal, or gambling advice.
              </p>
            </div>
          </>
        )}
      </section>

      <AuthModal
        isOpen={isAuthOpen}
        initialMode={authMode}
        onClose={() => setIsAuthOpen(false)}
        onAuthSuccess={() => {
          setIsLoggedIn(true);
          setIsAuthOpen(false);
          setError("");
        }}
      />
    </main>
  );
}

function Welcome({ onSuggestion, inputRef }) {
  return (
    <section className="welcome-card">
      <div className="welcome-icon">
        <Icon name="spark" />
      </div>
      <p className="eyebrow">FINANCIAL RESEARCH ASSISTANT</p>
      <h2>How can I help with your financial research?</h2>
      <p>
        Ask a question and FinAssist will retrieve trusted evidence before the
        Risk Analysis Agent explains the possible risks.
      </p>
      <div className="suggestions">
        {suggestions.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => {
              onSuggestion(item.question);
              inputRef.current?.focus();
            }}
          >
            <span>{item.label}</span>
            <Icon name="arrow" />
          </button>
        ))}
      </div>
    </section>
  );
}

function MessageCard({ message, onSuggestion }) {
  // Support both old and new backend response formats.
  const metadata = message.extra_data || message.metadata || {};

  const riskAnalysis = metadata.risk_analysis;
  const decisionSupport = metadata.decision_support;
  const suggestedQuestions = metadata.suggested_questions || [];
  const retrieval = metadata.retrieval;

  const isUser = message.role === "user";

  return (
    <article className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="avatar">{isUser ? "You" : "FA"}</div>

      <div className="message-body">
        <p className="message-role">
          {isUser ? "You" : "FinAssist"}
        </p>

        {riskAnalysis ? (
          <RiskAnalysisResult
            analysis={riskAnalysis}
            evidence={retrieval?.evidence}
          />
        ) : (
          <>
            <div className="message-text">
              {message.content}
            </div>

            {retrieval?.evidence?.length > 0 && (
              <EvidenceCards evidence={retrieval.evidence} />
            )}
          </>
        )}

        {decisionSupport && (
          <DecisionSupportResult support={decisionSupport} />
        )}

        {suggestedQuestions?.length > 0 && (
          <SuggestedQuestions
            questions={suggestedQuestions}
            onSelect={onSuggestion}
          />
        )}
      </div>
    </article>
  );
}

function RiskAnalysisResult({ analysis, evidence }) {
  const sources = new Map(
    (analysis.sources || []).map((source) => [String(source.id), source]),
  );
  return (
    <section className="risk-result" aria-label="Risk analysis">
      <div className="risk-summary">
        <p className="result-heading">Executive Risk Summary</p>
        <p>{analysis.summary}</p>
      </div>
      <div className="identified-risks">
        <p className="result-heading">Identified Risk Breakdown</p>
        {analysis.risks?.length > 0 ? (
          analysis.risks.map((risk) => (
            <article className="risk-card" key={risk.name}>
              <div className="risk-card-heading">
                <h3>{risk.name}</h3>
                <span
                  className={`risk-level risk-level-${String(risk.level).toLowerCase()}`}
                >
                  {risk.level}
                </span>
              </div>
              <p className="risk-explanation">{risk.explanation}</p>
              {risk.level_reason && (
                <div className="risk-level-reason">
                  <strong>Severity Rationale:</strong> {risk.level_reason}
                </div>
              )}
              <div className="risk-sources">
                <span>
                  Supporting source{risk.evidence_ids?.length === 1 ? "" : "s"}
                </span>
                {risk.evidence_ids?.map((evidenceId) => {
                  const source = sources.get(String(evidenceId));
                  if (!source) return null;
                  return source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      key={String(evidenceId)}
                    >
                      {source.source || "Retrieved source"}
                      <Icon name="external" />
                    </a>
                  ) : (
                    <strong key={String(evidenceId)}>
                      {source.source || "Retrieved source"}
                    </strong>
                  );
                })}
              </div>
            </article>
          ))
        ) : (
          <p className="no-risks">
            The available evidence did not support a specific risk category.
          </p>
        )}
      </div>

      {evidence?.length > 0 && <EvidenceCards evidence={evidence} />}

      <div className="risk-disclaimer-card" role="note">
        <div className="disclaimer-header">
          <Icon name="shield" />
          <span>AI Model Notice & Educational Disclaimer</span>
        </div>
        <p className="disclaimer-body">
          {analysis.disclaimer ||
            "This is educational financial information, not personalised investment or lending advice. Consider a qualified financial professional for decisions about your circumstances."}
        </p>
        <p className="disclaimer-notice">
          ⚠️ <em>FinAssist is an AI assistant. AI models can make mistakes or have incomplete market context. Always verify crucial financial decisions with certified professionals or official regulatory disclosures.</em>
        </p>
      </div>
    </section>
  );
}

function DecisionSupportResult({ support }) {
  return (
    <section className="decision-support">
      <p className="result-heading">Things to consider</p>

      {support.considerations?.map((item) => (
        <article className="decision-card" key={item.risk}>
          <h3>{item.risk}</h3>

          {item.things_to_consider?.map((consideration, index) => (
  <p key={index}>{consideration}</p>
))}
        </article>
      ))}

      {support.questions_to_consider?.length > 0 && (
        <div className="decision-questions">
          <p className="result-heading">Questions to ask before deciding</p>

          {support.questions_to_consider.map((question, index) => (
            <p key={index}>• {question}</p>
          ))}
        </div>
      )}

      {support.disclaimer && (
        <p className="risk-disclaimer">
          {support.disclaimer}
        </p>
      )}
    </section>
  );
}
function SuggestedQuestions({ questions, onSelect }) {
  return (
    <section
      className="message-suggestions"
      aria-label="Suggested financial questions"
    >
      <p>Suggested questions</p>
      <div>
        {questions.map((item) => (
          <button
            key={item.question}
            type="button"
            onClick={() => onSelect(item.question)}
          >
            {item.label}
            <Icon name="arrow" />
          </button>
        ))}
      </div>
    </section>
  );
}

function EvidenceCards({ evidence }) {
  const sortedEvidence = [...(evidence || [])].sort((a, b) => {
    const scoreA = typeof a.score === "number" ? a.score : 0;
    const scoreB = typeof b.score === "number" ? b.score : 0;
    return scoreB - scoreA;
  });

  return (
    <section className="evidence-wrap">
      <p className="evidence-heading">
        <Icon name="sources" /> Retrieved evidence{" "}
        <span>
          {sortedEvidence.length} source{sortedEvidence.length === 1 ? "" : "s"}
        </span>
      </p>
      <div className="evidence-grid">
        {sortedEvidence.map((item, index) => (
          <article className="evidence-card" key={item.id || item.url || index}>
            <div className="evidence-card-top">
              <span>{sourceDomain(item.url)}</span>
              {typeof item.score === "number" && (
                <b>{Math.round(item.score * 100)}% relevance</b>
              )}
            </div>
            {item.url ? (
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.source || "Open source"}
                <Icon name="external" />
              </a>
            ) : (
              <strong>{item.source || "Source"}</strong>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function sourceDomain(url) {
  try {
    return new URL(url).hostname.replace("www.", "");
  } catch {
    return "Trusted source";
  }
}

function Icon({ name }) {
  const paths = {
    shield: (
  <>
    <path d="M12 3 19 6v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3Z" />
    <path d="m9 12 2 2 4-4" />
  </>
),
    plus: (
      <>
        <path d="M12 5v14M5 12h14" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </>
    ),
    moon: <path d="M20 15.2A8.3 8.3 0 0 1 8.8 4 8.5 8.5 0 1 0 20 15.2Z" />,
    warning: (
      <>
        <path d="m12 3 9 16H3L12 3Z" />
        <path d="M12 9v4M12 17h.01" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" />
      </>
    ),
    send: (
      <>
        <path d="m21 3-7.5 18-3.4-7.1L3 10.5 21 3Z" />
        <path d="m10.1 13.9 4.5-4.5" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m13 6 6 6-6 6" />
      </>
    ),
    sources: (
      <>
        <rect x="4" y="5" width="11" height="14" rx="1" />
        <path d="M8 9h4M8 12h4M8 15h3" />
        <path d="M15 8h5v11H9" />
      </>
    ),
    card: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M3 10h18M7 15h3" />
      </>
    ),
    external: (
      <>
        <path d="M14 5h5v5M19 5l-8 8" />
        <path d="M17 13v5a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2V8a2 2 0 0 1 1-1h5" />
      </>
    ),
    flask: (
      <>
        <path d="M9 3h6M10 3v6l-5 8.5A2.3 2.3 0 0 0 7 21h10a2.3 2.3 0 0 0 2-3.5L14 9V3" />
        <path d="M8.2 15h7.6" />
      </>
    ),
    trash: (
      <>
        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6" />
      </>
    ),
  };
  return (
    <svg
      className={`icon icon-${name}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function currentViewFromHash() {
  return window.location.hash === "#/subscription" ? "subscription" : "chat";
}

createRoot(document.getElementById("root")).render(<App />);


