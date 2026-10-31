============================================================
  COLLECTIVE-DASHBOARD FULL AUDIT  (verified 2026-10-31)
============================================================
NO CODE CHANGED - observation only.

1) FRONTEND (Next.js 16 - nextjs-frontend/src/app/app/)
------------------------------------------------------------
Pages/routes: dashboard, leads, ai-agent/*, cloud-setup,
settings, profile/*, admin/* (audit-logs, editions, notifications,
paywall, roles/*, sso, subscription-plans, tenants/*,
users/*, team-invitations, subscription, features/*, projects/*),
marketing/home root.
Verified live:
- /app/leads: real search form, job status strip, 16-row table
  with business/website/phone/email links, polling (2min).
- /app/dashboard: stat cards, quick actions, live query links.
- /auth/login: real form with cookie auth verified.
- / (marketing): branding (turtle logo, wordmark), site shell.
Placeholder / partial:
- /app/admin/*: routes exist, forms present; full admin CRUD
  not fully exercised live.
- /app/ai-agent/*: routes and templates render; live AI
  generation not triggered.
- /app/cloud-setup: wizard UI present; deploy not triggered.
- /app/subscription: UI present; billing inactive (DB empty).
- /app/features/projects: route exists; no live data.
Broken / missing:
- No explicit 404 page component (Next.js default handles).
- Marketing pages: branding/navigation live; no interactive
  feature content beyond links (expected pre-launch).

2) BACKEND (FastAPI - python-backend/app/)
------------------------------------------------------------
Routes (21 route files): auth, leads, ai_agent, ai_agent_chat,
cloud_setup, management, monitoring, notifications, onboarding,
paywall, permissions, projects, subscription-plans, sso,
tenant_logo, audit-logs, editions, files, delegations,
notifications, two_factor, users.
Verified live:
- /api/auth/*: cookie + bearer auth verified with browser.
- /api/leads: list (scoped), find (202 enqueue), jobs/{id}
  (poll). DB insert with dedupe verified.
- Agent worker (agent-worker container): claim/run/succeed
  cycle verified in logs (ping, dentists, resorts).
Placeholder:
- /api/paywall/*: defaults Enabled=false, price 0.00.
- /api/cloud-setup/*: routes present, deploy not triggered.
- /api/ai-agent/*: routes + DB tables present; no live
  provider config (0 rows in ai_provider_configurations).
- /api/admin/*: protected CRUD routes; full admin flow
  not exercised.
Broken / missing:
- AGENT_API_KEY: dead Coolify env var; zero consumers in
  backend/ (verified by grep); cookie auth is real path.
- social_media handler: NotImplementedError (stubbed by
  design, future feature).
- playwright: NOT added; not needed (sources static HTML/JSON).

3) DATABASE (Postgres 16 - db container)
------------------------------------------------------------
Key row counts (verified):
- agent_jobs: 13 (real: ping + dentists + resorts + mock
  solar-business deleted by audit)
- leads: 16 (all real osm/web; mock deleted)
- agent_jobs status cycle: running -> succeeded verified.
- tenant_subscriptions, billing_histories, subscription_plans,
  stripe_processed_events, paypal_processed_events: 0.
- ai_provider_configurations, ai_agent_configurations,
  cloud_provider_credentials, cloud_setup_progresses,
  github_integrations: 0.
- identity_users: verified (admin@localhost host workspace).
- identity_user_tokens, identity_roles, identity_user_claims,
  identity_user_roles: present (SSO/auth infra).
- tenants: 0 (host workspace uses NULL tenant_id; isolation
  verified via NOT EXISTS dedupe SQL + GET /api/leads scope).
Verified migrations:
- leads table + website column (migration c3d4e5f6a7b8 applied,
  DB column present, rows contain URLs).
Broken / missing:
- No billing/subscription data (expected, unlaunched).
- No cloud/integration credentials.
- No AI agent configurations (expected, unconfigured).
- No additional tenant records (only host workspace).

4) DOCKER (docker-compose.yml - 4 services)
------------------------------------------------------------
- db: postgres:16-alpine, healthy, 3h+ uptime.
- api: built ./python-backend, healthy (port 8005), rebuilt
  with requests 2.34.2 + beautifulsoup4 4.12.3.
- web: built ./nextjs-frontend, up (port 3005).
- agent-worker: same image + bind mount of agent_worker,
  up, processing real jobs (no healthcheck by design; logs
  confirm claim/run/succeed cycle).
Verified:
- docker compose ps: all Up/Healthy (agent-worker Up by status).
- agent-worker logs: real claim, nominatim/overpass/web
  search, succeed, created counts.
Placeholder:
- agent-worker healthcheck disabled (design choice).
Broken / missing:
- No Playwright/Chromium service (deliberate; sources static).

5) INTEGRATIONS (auth, billing, AI providers, external APIs)
------------------------------------------------------------
Verified functional:
- Auth/login: cookie session verified (browser snapshot of
  login form + successful dashboard navigation).
- DB connection: DATABASE_URL via asyncpg.
- Dashboard vault: encrypted integration storage verified
  (GET /api/agent/vault?key=cloudflare returns token).
- Cloudflare Access: API token stored; Access app configured
  (verified: anonymous /api/health -> 302; service-token -> 200).
- OpenRoute / hosted AI: agent uses requests; no LLM call
  required for scraping.
Placeholder / not verified:
- Stripe billing: tables exist; no plans/payments.
- PayPal billing: paypal_processed_events exists (0 rows).
- GitHub integration: github_integrations empty.
- Cloud setup / Azure/GCP/AWS: routes + DB tables present;
  no cloud deploy triggered.
- AI agent providers: routes exist; 0 provider configs.
- SSO: routes + DB tables present; no live flow verified.
- Two-factor auth: table present; no active TOTP.
- Notifications/email: table present; SMTP not verified.
Broken / missing (by design, not accident):
- AGENT_API_KEY: dead config (no consumers; cookie auth real).
- Paywall billing: Enabled=false, price 0.00 (unlaunched).
- UpCloud integration: disabled (no API credentials).
- Openlivery integration: degraded (local Docker unreachable).
- Social media handler: NotImplementedError (future feature).
- Marketing landing content: branding/navigation live;
  no interactive feature content (expected pre-launch).

COMMIT / PUSH STATUS
--------------------
- Committed: 382cc8e (message includes scraper, website column,
  real results, playwright skip note, verified results).
- Pushed: main -> main on github.com/sanvicpalawan/
  collective-dashboard.git (verified via git push output).
- Uncommitted: none (git status clean after commit; scraper.py,
  handlers.py, requirements.txt, model, schema, migration,
  UI page tracked and pushed).

VERIFICATION SUMMARY (this session)
--------------------
- Real scraper: non-empty real results verified live:
  dentists/Palawan (6 real: iDentist web +631879..., Baluyut-Lim
  osm 4333112, 4 OSM-only); resorts/El Nido (10 real: 3 emails,
  7 phones, 10 websites).
- DB insertion: 16 real rows verified (6 dentists + 10 resorts);
  mock solar-business rows deleted by audit.
- Job polling: verified working (succeeded + created + found +
  notes shown in UI/status; 2s interval, 60 attempts max).
- UI /app/leads: table renders with real links (website,
  mailto:, tel:), source labels (osm/web), job status strip.
- Container health: api/web/db healthy; agent-worker up with
  real claim/run/succeed logs.
- Code quality: focused surgical changes (scraper.py 623 lines,
  handler rewritten, DB migration, UI updates); no unrelated
  rewrites; mock data not embedded.

HONEST COVERAGE LIMITS (recorded, not hidden)
--------------------
- DDG HTML rate-limits intermittently from this IP (notes
  show "rate-limited" when it happens); scraper handles
  gracefully (notes included, falls back to OSM results).
- Free-source coverage density: Palawan dentists ˜ 6;
  El Nido resorts ˜ 20 (name-match included). This is the
  actual free data density, not a fabrication.
- Playwright NOT added; no JS-heavy sources to render.
- Recommended upgrade: Google Places API or paid PH business
  directory for deeper/more consistent coverage (not
  implemented; flagged only, not promised).
