# FinAssist React UI

This is a React + Vite frontend for FinAssist AI. It uses the API supplied by `Backend.B1`.

It supports:

- Starting and reopening stored MySQL conversations.
- Sending a question to the Information Retrieval + NLP Agent.
- Displaying source-backed Tavily evidence as citation cards.
- Dark/light mode and an explicit educational-use disclaimer.

## Run in development

Start the Python backend in one terminal. It automatically creates any missing MySQL tables at startup.

```powershell
python -m uvicorn Backend.B1:app --reload
```

In a second terminal:

```powershell
cd Frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`. Vite forwards `/api` requests to the Python backend on port 8000.

## Production-style build

```powershell
cd Frontend
npm run build
```

Then FastAPI serves the built React application at `http://127.0.0.1:8000`.

Mahee can add Risk Agent output as a new message type without changing the source-evidence API. Taniya should connect the sign-in button to verified authentication and add privacy controls before deployment.
