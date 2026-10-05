# SUMbody

**The little things add up.**

SUMbody is a personal value journal: record what you did, where in your life you added value, and how much value you believe it created. Over time, thousands of small contributions become a visible story.

## v1

- Fast mobile-first SUM entry
- Today vs. yesterday
- User-defined Life Areas with archival
- Explore/search by text, Life Area, and date
- Activity and impact insights
- Communication tracking
- Historical workbook importer
- Private account authentication

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export SECRET_KEY="development-secret"
flask --app app create-user
flask --app app run
```

## Historical import

Keep the original workbook outside the repository.

```bash
python scripts/import_legacy.py /path/to/SUMbody.xlsx your@email.com
```

The importer reads `Form Responses 1`, creates historical Life Areas as needed, preserves nullable communication data, and intentionally skips experimental values outside the standard 1–5 scale for manual review.

## Production

Designed for Gunicorn behind DreamHost/nginx/Apache proxying to a local application port. Production secrets and the SQLite database live on the server and are excluded from Git.

Production target: `sumbody.cameronjbock.com`
