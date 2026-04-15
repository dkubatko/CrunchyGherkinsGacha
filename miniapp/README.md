# Crunchy Gherkins TCG Mini App

React + TypeScript + Vite front-end for the Crunchy Gherkins TCG bot, embedded in Telegram as a Mini App.

## Setup

```bash
npm install
```

### Environment

Copy `.env.example` to `.env.production` and set `VITE_API_BASE_URL` to the FastAPI backend URL.

For local development no `.env` file is needed — the code falls back to `http://localhost:8000`.

| Variable | Description |
| --- | --- |
| `VITE_API_BASE_URL` | Base URL of the FastAPI backend |

### Development

```bash
npm run dev
```

### Production build

```bash
npm run build
```

The build output goes to `dist/`.
