# TenderHub Deployment

This project is configured for Render Web Service hosting with a Neon PostgreSQL production database.

## Local Development

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Local development falls back to SQLite when `DATABASE_URL` is not set.

## Render Build and Start Commands

Build command:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

Start command:

```bash
gunicorn core.wsgi:application
```

## Deployment Checklist

1. Push the `tenderapp` project to GitHub.
2. Create a Neon PostgreSQL database.
3. Copy the Neon `DATABASE_URL`.
4. Create a Render Web Service from the GitHub repository.
5. Add Render environment variables:
   - `SECRET_KEY`: a strong Django secret key.
   - `DEBUG`: `False`.
   - `ALLOWED_HOSTS`: your Render hostname, for example `tenderhub.onrender.com`.
   - `DATABASE_URL`: the Neon connection string.
   - `CSRF_TRUSTED_ORIGINS`: your Render origin, for example `https://tenderhub.onrender.com`.
6. Deploy the Render service.
7. Create a superuser:

```bash
python manage.py createsuperuser
```

8. Import tender data:

```bash
python manage.py import_tenders path/to/tender-data.xlsx
```

## Common Deployment Checks

- `DisallowedHost`: confirm `ALLOWED_HOSTS` contains the Render hostname without `https://`.
- Static files not loading: confirm `collectstatic` ran and `WhiteNoiseMiddleware` is enabled after `SecurityMiddleware`.
- CSRF errors: confirm `CSRF_TRUSTED_ORIGINS` contains the full Render origin with `https://`.
- Database errors: confirm Neon `DATABASE_URL` is set and migrations ran successfully.
- Missing tables: run `python manage.py migrate` in the Render shell.
- `collectstatic` failures: check static file references and make sure dependencies installed from `requirements.txt`.
- Production safety: keep `DEBUG=False` on Render.
