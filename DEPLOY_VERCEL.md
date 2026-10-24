# Deploy TOTE + PackWise on Vercel

Deploy three Vercel projects from this repository: the API + C++ engine together, then one project for each frontend.

## 1. Deploy the API and packing engine

Create a Vercel project from this repository with the repository root (`.`) as its Root Directory. Set **Framework Preset** to **Services**. The root `vercel.json` routes API requests to FastAPI and privately binds FastAPI to the C++ packer container.

Add a hosted PostgreSQL database through Vercel Marketplace (Neon is one option). Add these project environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string from the database provider |
| `PACKWISE_WORKER_CODE` | Private warehouse sign-in code |
| `ADMIN_ACCESS_CODE` | Private admin sign-in code |
| `PACKING_ALGORITHM` | `optimizer2` |
| `CORS_ORIGINS` | Comma-separated production URLs for the TOTE and PackWise projects; add after their first deploy |

Deploy this project. Its API health endpoint is `/api/health`.

## 2. Deploy the TOTE storefront

Create another Vercel project from the same repository. Set Root Directory to `tote-frontend`, Framework Preset to **Vite**, Build Command to `npm run build`, and Output Directory to `dist`. Add `VITE_API_URL` with the API project’s HTTPS URL, without a trailing slash, then deploy.

## 3. Deploy PackWise

Create a third project from the same repository. Use Root Directory `packwise-frontend` and the same Vite build settings. Set `VITE_API_URL` to the same API URL and deploy.

After both frontends have production URLs, put those exact origins in the API project’s `CORS_ORIGINS` variable and redeploy the API project. Check `/api/health`, then try a storefront checkout and the PackWise order queue.

The database must be PostgreSQL: Vercel Functions do not provide shared persistent local disk for SQLite. The C++ engine runs as a stateless HTTP container and is called privately by the API.
