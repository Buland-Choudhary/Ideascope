# Ideascope frontend

React + TypeScript + Vite shell for the lesson player. See
[`../docs/PLAN.md`](../docs/PLAN.md) §6 for the full design. At Phase 0 this is
a "hello world" that renders the title and pings the backend health endpoint.

## Development

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Point the app at a non-default backend with `VITE_API_BASE_URL`:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Checks

```bash
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit
npm run test        # Vitest
npm run build       # production build (tsc -b + vite build)
```
