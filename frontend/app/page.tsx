"use client";

import { useState } from "react";

export default function Home() {
  const [question, setQuestion] = useState("");

  const handleAnalyze = async () => {
  if (!question.trim()) return;

  try {
    const response = await fetch("http://localhost:8000/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: question,
      }),
    });

    if (!response.ok) {
      throw new Error("Failed to analyze question");
    }

    const data = await response.json();

    console.log("Backend response:", data);
  } catch (error) {
    console.error("Analysis error:", error);
  }
};

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-bold">FinAssist AI</h1>
            <p className="text-xs text-slate-400">
              Agentic Financial Intelligence
            </p>
          </div>

          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            System Online
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl">
        {/* Sidebar */}
        <aside className="hidden min-h-[calc(100vh-73px)] w-60 border-r border-slate-800 p-5 md:block">
          <nav className="space-y-2">
            <NavItem label="Dashboard" active />
            <NavItem label="Analysis" />
            <NavItem label="Agents" />
            <NavItem label="History" />
            <NavItem label="Settings" />
          </nav>
        </aside>

        {/* Main Content */}
        <section className="flex-1 p-6 md:p-10">
          <div className="mb-8">
            <p className="mb-2 text-sm text-blue-400">Financial Intelligence</p>

            <h2 className="text-3xl font-bold">
              What would you like to analyze?
            </h2>

            <p className="mt-2 text-slate-400">
              Ask FinAssist AI a financial research or risk question.
            </p>
          </div>

          {/* Question Box */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Example: Analyze the financial risk of NVIDIA..."
              className="min-h-32 w-full resize-none bg-transparent text-white outline-none placeholder:text-slate-500"
            />

            <div className="mt-4 flex justify-end">
              <button
                onClick={handleAnalyze}
                className="rounded-lg bg-blue-600 px-6 py-3 font-medium transition hover:bg-blue-500"
              >
                Analyze →
              </button>
            </div>
          </div>

          {/* Agent Status */}
          <div className="mt-10">
            <h3 className="mb-4 text-lg font-semibold">Agent Status</h3>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <AgentCard
                name="Security Agent"
                description="Input validation"
              />

              <AgentCard
                name="IR / NLP Agent"
                description="Information retrieval"
              />

              <AgentCard
                name="Risk Agent"
                description="Risk assessment"
              />

              <AgentCard
                name="Orchestrator"
                description="Agent coordination"
              />
            </div>
          </div>

          {/* Disclaimer */}
          <div className="mt-10 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4">
            <p className="text-sm text-amber-300">
              ⚠ Responsible AI Notice
            </p>

            <p className="mt-1 text-xs text-slate-400">
              FinAssist AI provides educational financial analysis and should
              not be considered professional financial advice.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function NavItem({
  label,
  active = false,
}: {
  label: string;
  active?: boolean;
}) {
  return (
    <button
      className={`w-full rounded-lg px-4 py-3 text-left text-sm transition ${
        active
          ? "bg-blue-600/10 text-blue-400"
          : "text-slate-400 hover:bg-slate-900 hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

function AgentCard({
  name,
  description,
}: {
  name: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="h-3 w-3 rounded-full bg-emerald-400" />

        <span className="text-xs text-emerald-400">Online</span>
      </div>

      <h4 className="font-semibold">{name}</h4>

      <p className="mt-1 text-sm text-slate-500">{description}</p>
    </div>
  );
}