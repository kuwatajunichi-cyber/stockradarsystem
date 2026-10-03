# web-ui-static

Internal first-live static UI (Workers Static Assets). Deploy:

    npx wrangler deploy --config workers/web-ui-static/wrangler.jsonc

`workers_dev` must stay true. Do not copy github-cron-dispatcher.
Publishable key is a Wrangler secret (`SUPABASE_PUBLISHABLE_KEY`). Never commit it.
BFF origin is `BFF_ORIGIN`. Screen body talks to BFF with `Authorization: Bearer`.
