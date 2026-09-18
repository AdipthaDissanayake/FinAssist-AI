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
        body: JSON.stringify({ content, top_k: 5 }),
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
            isLoggedIn={isLoggedIn}
            onOpenAuth={(mode) => {
              setAuthMode(mode || "register");
              setIsAuthOpen(true);
            }}
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
                  <ChatMessage
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

function ChatMessage({ message, onSuggestion }) {
  const [feedback, setFeedback] = useState(null);
  const [copied, setCopied] = useState(false);

  // Support both old and new backend response formats.
  const metadata = message.extra_data || message.metadata || {};

  const riskAnalysis = metadata.risk_analysis;
  const decisionSupport = metadata.decision_support;
  const suggestedQuestions = metadata.suggested_questions || [];
  const retrieval = metadata.retrieval;
  const isUser = message.role === "user";

  const handleShare = () => {
    let shareText = message.content || "";

    if (riskAnalysis) {
      const summaryText = riskAnalysis.summary
        ? `Summary:\n${riskAnalysis.summary}\n\n`
        : "";

      const risksText = (riskAnalysis.risks || [])
        .map(
          (risk) =>
            `• ${risk.name} (${risk.level}): ${risk.explanation}`,
        )
        .join("\n");

      shareText =
        `FinAssist Financial Risk Analysis:\n\n` +
        `${summaryText}Identified Risks:\n${risksText}`;
    }

    navigator.clipboard.writeText(shareText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <article className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="avatar">{isUser ? "You" : "FA"}</div>

      <div className="message-body">
        <p className="message-role">
          {isUser ? "You" : "FinAssist"}
        </p>

        {riskAnalysis ? (
          <>
            <RiskAnalysisResult
              analysis={riskAnalysis}
              evidence={retrieval?.evidence}
            />

            {decisionSupport && (
              <DecisionSupportResult support={decisionSupport} />
            )}

            <AIModelDisclaimer customText={riskAnalysis.disclaimer} />
          </>
        ) : (
          <>
            <div className="message-text">
              {message.content}
            </div>

            {retrieval?.evidence?.length > 0 && (
              <EvidenceCards evidence={retrieval.evidence} />
            )}

            {decisionSupport && (
              <DecisionSupportResult support={decisionSupport} />
            )}

            {!isUser && <AIModelDisclaimer />}
          </>
        )}

        {suggestedQuestions?.length > 0 && (
          <SuggestedQuestions
            questions={suggestedQuestions}
            onSelect={onSuggestion}
          />
        )}

        {!isUser && (
          <div className="message-actions">
            <button
              type="button"
              className={`action-btn ${
                feedback === "like" ? "active like" : ""
              }`}
              onClick={() =>
                setFeedback(feedback === "like" ? null : "like")
              }
              title="Helpful response"
              aria-label="Helpful response"
            >
              <Icon name="thumbs-up" />
              <span>Helpful</span>
            </button>

            <button
              type="button"
              className={`action-btn ${
                feedback === "dislike" ? "active dislike" : ""
              }`}
              onClick={() =>
                setFeedback(feedback === "dislike" ? null : "dislike")
              }
              title="Not helpful"
              aria-label="Not helpful"
            >
              <Icon name="thumbs-down" />
              <span>Not helpful</span>
            </button>

            <button
              type="button"
              className={`action-btn ${copied ? "copied" : ""}`}
              onClick={handleShare}
              title="Share / Copy response"
              aria-label="Share response"
            >
              <Icon name={copied ? "check" : "share"} />
              <span>{copied ? "Copied!" : "Share"}</span>
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

function RiskAnalysisResult({ analysis, evidence }) {
  const sources = new Map(
    (analysis.sources || []).map((source) => [String(source.id), source]),
  );

  const levelRank = { high: 3, medium: 2, low: 1 };
  const sortedRisks = [...(analysis.risks || [])].sort((a, b) => {
    const rankA = levelRank[String(a.level).toLowerCase()] || 0;
    const rankB = levelRank[String(b.level).toLowerCase()] || 0;
    return rankB - rankA;
  });

  return (
    <section className="risk-result" aria-label="Risk analysis">
      <div className="risk-summary">
        <h2 className="section-heading">
          <Icon name="spark" /> Executive Risk Summary
        </h2>
        <p className="summary-text">{analysis.summary}</p>
      </div>
      <div className="identified-risks">
        <h2 className="section-heading">
          <Icon name="warning" /> Identified Risk Breakdown
        </h2>
        {sortedRisks?.length > 0 ? (
          sortedRisks.map((risk) => (
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

      {(evidence?.length > 0 ? evidence : (analysis?.sources?.length > 0 ? analysis.sources : []))?.length > 0 && (
        <EvidenceCards evidence={evidence?.length > 0 ? evidence : analysis.sources} />
      )}
    </section>
  );
}

function AIModelDisclaimer({ customText }) {
  return (
    <div className="risk-disclaimer-card" role="note">
      <div className="disclaimer-header">
        <Icon name="shield" />
        <span>AI Model Notice & Educational Disclaimer</span>
      </div>
      <p className="disclaimer-body">
        {customText ||
          "This is educational information, not personalised financial, investment, or lending advice. FinAssist is an AI assistant and can make mistakes or have incomplete market context. Consider a qualified financial professional for decisions about your circumstances."}
      </p>
      <p className="disclaimer-notice">
        ⚠️ <em>FinAssist is an AI assistant. AI models can make mistakes or have incomplete market context. Always verify crucial financial decisions with certified professionals or official regulatory disclosures.</em>
      </p>
    </div>
  );
}

function DecisionSupportResult({ support }) {
  if (!support) return null;
  const considerations = support.considerations || [];
  const questions = support.questions_to_consider || [];
  if (considerations.length === 0 && questions.length === 0) return null;

  return (
    <section className="decision-support" aria-label="Financial decision considerations">
      <h2 className="section-heading">
        <Icon name="spark" /> Key Decision-Making Considerations
      </h2>

      {considerations.map((item, idx) => (
        <article className="decision-card" key={item.risk || idx}>
          <div className="decision-card-heading">
            <h3>{item.risk}</h3>
            {item.level && (
              <span className={`risk-level risk-level-${String(item.level).toLowerCase()}`}>
                {item.level}
              </span>
            )}
          </div>

          {item.things_to_consider?.map((consideration, index) => (
            <p key={index}>{consideration}</p>
          ))}
        </article>
      ))}

      {questions.length > 0 && (
        <div className="decision-questions">
          <p className="result-heading">Questions to ask before deciding</p>
          <ul>
            {questions.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
function SuggestedQuestions({ questions, onSelect }) {
  return (
    <section className="message-suggestions" aria-label="Suggested follow-up questions">
      <p>Suggested questions to explore</p>
      <div>
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onSelect(question)}
          >
            <span>{question}</span>
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

  if (sortedEvidence.length === 0) return null;

  return (
    <div className="verified-evidence-block">
      <div className="evidence-block-header">
        <h2 className="section-heading">
          <Icon name="sources" /> Verified Source Evidence
        </h2>
        <span className="evidence-count-badge">
          {sortedEvidence.length} source{sortedEvidence.length === 1 ? "" : "s"} analyzed
        </span>
      </div>

      <p className="evidence-intro-message">
        FinAssist retrieved and cross-referenced the following verified regulatory frameworks, central bank guidelines, and institutional disclosures to substantiate the risk analysis above:
      </p>

      <section className="evidence-section" aria-label="Retrieved Evidence Sources">
        <div className="evidence-list">
          {sortedEvidence.map((item, index) => {
            const domain = sourceDomain(item.url);
            const scorePercent = typeof item.score === "number" ? Math.round(item.score * 100) : null;
            const title = item.source || item.title || "Financial Disclosure / Policy Document";

            return (
              <div className="evidence-item-row" key={item.id || item.url || index}>
                <div className="evidence-index-badge">
                  <span>{index + 1}</span>
                </div>

                <div className="evidence-info">
                  <div className="evidence-meta-row">
                    <span className="evidence-domain-pill">{domain}</span>
                    {scorePercent !== null && (
                      <span className="evidence-score-pill">
                        <span className="score-dot" />
                        {scorePercent}% relevance
                      </span>
                    )}
                  </div>

                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="evidence-link-title"
                      title={`Visit ${title}`}
                    >
                      <span>{title}</span>
                      <Icon name="external" />
                    </a>
                  ) : (
                    <span className="evidence-static-title">{title}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
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
    
    "thumbs-up": (
      <>
        <path d="M7 10v12" />
        <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3Z" />
      </>
    ),
    "thumbs-down": (
      <>
        <path d="M17 14V2" />
        <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3Z" />
      </>
    ),
    share: (
      <>
        <circle cx="18" cy="5" r="3" />
        <circle cx="6" cy="12" r="3" />
        <circle cx="18" cy="19" r="3" />
        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
        <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
      </>
    ),
    check: (
      <>
        <polyline points="20 6 9 17 4 12" />
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
      {paths[name] || null}
    </svg>
  );
}

export const MessageCard = ChatMessage;

function currentViewFromHash() {
  return window.location.hash === "#/subscription" ? "subscription" : "chat";
}

createRoot(document.getElementById("root")).render(<App />);


