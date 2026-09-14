import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const suggestions = [
  { label: "Loan repayment risks", question: "What are the risks of taking a loan?" },
  { label: "Investment concentration risk", question: "What is concentration risk in investing?" },
  { label: "Fixed deposit considerations", question: "What should I know before putting money into a fixed deposit?" },
  { label: "Financial risks of betting", question: "What are the financial risks associated with betting?" },
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const rawBody = await response.text();
  let payload = null;
  try { payload = rawBody ? JSON.parse(rawBody) : null; }
  catch {
    if (!response.ok) throw new Error(`The server returned an error (${response.status}). Please try again shortly.`);
    throw new Error("The server returned an unexpected response. Please refresh and try again.");
  }
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Request failed. Please try again.");
  return payload;
}

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("finassist-theme") || "dark");
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const messageEndRef = useRef(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("finassist-theme", theme);
  }, [theme]);
  useEffect(() => { loadChats(); }, []);
  useEffect(() => { messageEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, isSending]);

  async function loadChats() {
    try { setChats(await api("/api/chats")); } catch (requestError) { setError(requestError.message); }
  }
  async function openChat(chatId) {
    try {
      setError("");
      const data = await api(`/api/chats/${chatId}/messages`);
      setActiveChatId(chatId);
      setMessages(data.messages);
    } catch (requestError) { setError(requestError.message); }
  }
  function startNewChat() {
    setActiveChatId(null);
    setMessages([]);
    setError("");
    inputRef.current?.focus();
  }
  function useSuggestion(question) {
    setDraft(question);
    inputRef.current?.focus();
  }
  async function sendQuestion(question = draft) {
    const content = question.trim();
    if (!content || isSending) return;
    setIsSending(true);
    setError("");
    try {
      let chatId = activeChatId;
      if (!chatId) {
        const chat = await api("/api/chats", { method: "POST", body: JSON.stringify({}) });
        chatId = chat.id;
        setActiveChatId(chatId);
      }
      const result = await api(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content, top_k: 3 }),
      });
      setMessages((current) => [...current, result.user_message, result.assistant_message]);
      setDraft("");
      await loadChats();
    } catch (requestError) { setError(requestError.message); }
    finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  return <main className="app-shell">
    <aside className="sidebar" aria-label="Conversation history">
      <button className="brand" type="button" onClick={startNewChat} aria-label="Start a new chat"><span className="brand-mark">F</span><span>FinAssist <b>AI</b></span></button>
      <button className="new-chat-button" type="button" onClick={startNewChat}><Icon name="plus" /> New chat</button>
      <p className="sidebar-heading">Conversations</p>
      <nav className="chat-list" aria-label="Saved conversations">
        {chats.length === 0 && <p className="empty-state">Your saved research will appear here.</p>}
        {chats.map((chat) => <button className={`chat-item ${chat.id === activeChatId ? "active" : ""}`} key={chat.id} type="button" onClick={() => openChat(chat.id)}>
          <span className="chat-item-title">{chat.title}</span><span className="chat-item-preview">{chat.preview || "No messages yet"}</span>
        </button>)}
      </nav>
      <div className="sidebar-footer"><span className="status-dot" /> History saved · sign-in pending</div>
    </aside>

    <section className="conversation-panel">
      <header className="topbar">
        <div><h1>FinAssist AI</h1><p>Source-backed financial research</p></div>
        <div className="top-actions">
          <span className="source-status"><span className="status-dot" /> Trusted sources</span>
          <button className="theme-toggle" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle colour theme"><Icon name={theme === "dark" ? "sun" : "moon"} /> {theme === "dark" ? "Light" : "Dark"}</button>
        </div>
      </header>

      <section className="message-view" aria-live="polite">
        {error && <div className="error-notice" role="alert"><Icon name="warning" />{error}</div>}
        {messages.length === 0 ? <Welcome onSuggestion={useSuggestion} inputRef={inputRef} /> : messages.map((message) => <MessageCard key={message.id} message={message} onSuggestion={useSuggestion} />)}
        {isSending && <div className="retrieving"><span className="loading-dot" /><span>Searching trusted financial sources...</span></div>}
        <div ref={messageEndRef} />
      </section>

      <div className="composer-area">
        <form className="composer" onSubmit={(event) => { event.preventDefault(); sendQuestion(); }}>
          <label className="sr-only" htmlFor="question-input">Financial question</label>
          <textarea id="question-input" ref={inputRef} value={draft} rows="1" maxLength="2000" onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendQuestion(); } }} placeholder="Ask about loans, savings, investments, or interest rates..." />
          <button className="send-button" type="submit" disabled={isSending || !draft.trim()} aria-label="Send question"><Icon name="send" /></button>
        </form>
        <p className="disclaimer">Educational information only — not personalised financial, investment, legal, or gambling advice.</p>
      </div>
    </section>
  </main>;
}

function Welcome({ onSuggestion, inputRef }) {
  return <section className="welcome-card">
    <div className="welcome-icon"><Icon name="spark" /></div>
    <p className="eyebrow">FINANCIAL RESEARCH ASSISTANT</p>
    <h2>How can I help with your financial research?</h2>
    <p>Ask a question and FinAssist will retrieve trusted evidence before the Risk Analysis Agent explains the possible risks.</p>
    <div className="suggestions">
      {suggestions.map((item) => <button key={item.label} type="button" onClick={() => { onSuggestion(item.question); inputRef.current?.focus(); }}><span>{item.label}</span><Icon name="arrow" /></button>)}
    </div>
  </section>;
}

function MessageCard({ message, onSuggestion }) {
  const retrieval = message.metadata?.retrieval;
  const suggestedQuestions = message.metadata?.suggested_questions;
  const isUser = message.role === "user";
  return <article className={`message ${isUser ? "user" : "assistant"}`}>
    <div className="avatar">{isUser ? "You" : "FA"}</div>
    <div className="message-body">
      <p className="message-role">{isUser ? "You" : "FinAssist"}</p>
      <div className="message-text">{message.content}</div>
      {retrieval?.evidence?.length > 0 && <EvidenceCards evidence={retrieval.evidence} />}
      {suggestedQuestions?.length > 0 && <SuggestedQuestions questions={suggestedQuestions} onSelect={onSuggestion} />}
    </div>
  </article>;
}

function SuggestedQuestions({ questions, onSelect }) {
  return <section className="message-suggestions" aria-label="Suggested financial questions">
    <p>Suggested questions</p>
    <div>{questions.map((item) => <button key={item.question} type="button" onClick={() => onSelect(item.question)}>{item.label}<Icon name="arrow" /></button>)}</div>
  </section>;
}

function EvidenceCards({ evidence }) {
  return <section className="evidence-wrap">
    <p className="evidence-heading"><Icon name="sources" /> Retrieved evidence <span>{evidence.length} source{evidence.length === 1 ? "" : "s"}</span></p>
    <div className="evidence-grid">
      {evidence.map((item) => <article className="evidence-card" key={item.id}>
        <div className="evidence-card-top"><span>{sourceDomain(item.url)}</span>{typeof item.score === "number" && <b>{Math.round(item.score * 100)}% relevance</b>}</div>
        {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.source || "Open source"}<Icon name="external" /></a> : <strong>{item.source || "Source"}</strong>}
        <p>{item.text || "No preview available."}</p>
      </article>)}
    </div>
  </section>;
}

function sourceDomain(url) {
  try { return new URL(url).hostname.replace("www.", ""); } catch { return "Trusted source"; }
}

function Icon({ name }) {
  const paths = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    sun: <><circle cx="12" cy="12" r="3.5" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    moon: <path d="M20 15.2A8.3 8.3 0 0 1 8.8 4 8.5 8.5 0 1 0 20 15.2Z" />,
    warning: <><path d="m12 3 9 16H3L12 3Z" /><path d="M12 9v4M12 17h.01" /></>,
    spark: <><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" /></>,
    send: <><path d="m21 3-7.5 18-3.4-7.1L3 10.5 21 3Z" /><path d="m10.1 13.9 4.5-4.5" /></>,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    sources: <><rect x="4" y="5" width="11" height="14" rx="1" /><path d="M8 9h4M8 12h4M8 15h3" /><path d="M15 8h5v11H9" /></>,
    external: <><path d="M14 5h5v5M19 5l-8 8" /><path d="M17 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5" /></>,
  };
  return <svg className={`icon icon-${name}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

createRoot(document.getElementById("root")).render(<App />);
