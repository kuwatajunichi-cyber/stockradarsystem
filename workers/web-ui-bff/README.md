# web-ui-bff

Authenticated BFF for internal first live. Deploy:

    npx wrangler deploy --config workers/web-ui-bff/wrangler.jsonc

`workers_dev` must stay true. CORS allowlist is `STATIC_ORIGIN` only.
Secrets: `SUPABASE_SECRET_KEY`, `SUPABASE_PUBLISHABLE_KEY`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. Vars include `R2_PUBLIC_BUCKET=false`.
Never log signed URLs. Unauthenticated mint is 401.
