# GPFE PROC HUB Deployment

Panduan ini menggunakan server production generic dengan PostgreSQL `DATABASE_URL`.
Domain production utama:

- `inaprochub.gpfe.id`
- `www.inaprochub.gpfe.id` jika subdomain `www` diarahkan ke aplikasi

## Local Development

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Local development memakai SQLite saat `DATABASE_URL` tidak diset.

## Production Environment

Set environment variable berikut di server production:

```env
SECRET_KEY=
ENVIRONMENT=production
DEBUG=False
ALLOWED_HOSTS=inaprochub.gpfe.id,www.inaprochub.gpfe.id
CSRF_TRUSTED_ORIGINS=https://inaprochub.gpfe.id,https://www.inaprochub.gpfe.id
DATABASE_URL=
ENABLE_SECURE_SSL=True
SECURE_SSL_REDIRECT=True
ADMIN_URL_PATH=admin
LOGIN_LOCKOUT_SECONDS=60
```

`SECRET_KEY` wajib diisi dari environment. Jangan simpan secret, password, token, cookie, atau connection string di repository.

## Build and Start

Build command:

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
```

Start command:

```bash
gunicorn core.wsgi:application
```

## Deployment Checklist

1. Deploy folder `tenderapp` ke server production.
2. Siapkan PostgreSQL dan isi `DATABASE_URL`.
3. Isi environment variable production di atas.
4. Jalankan `python manage.py migrate`.
5. Jalankan `python manage.py collectstatic --noinput`.
6. Buat superuser:

```bash
python manage.py createsuperuser
```

7. Import tender data jika diperlukan:

```bash
python manage.py import_tenders path/to/tender-data.xlsx
```

8. Approve user vendor dari Django Admin dengan mengubah `is_active=True`.

## Security Checks

- Pastikan `DEBUG=False` di production.
- Pastikan `ALLOWED_HOSTS` hanya berisi domain production.
- Pastikan `CSRF_TRUSTED_ORIGINS` memakai origin HTTPS production.
- Pastikan HTTPS aktif sebelum mengaktifkan HSTS preload.
- Pastikan static files dilayani dari hasil `collectstatic`, bukan dari folder project mentah.
- Pastikan `.env`, `db.sqlite3`, backup database, log, credential, dan file export sensitif tidak berada di static/media publik.

## Common Deployment Checks

- `DisallowedHost`: cek `ALLOWED_HOSTS` tanpa `https://`.
- CSRF errors: cek `CSRF_TRUSTED_ORIGINS` memakai origin lengkap dengan `https://`.
- Static files tidak muncul: cek `collectstatic` dan `WhiteNoiseMiddleware`.
- Database errors: cek `DATABASE_URL` dan migration.
- Missing tables: jalankan `python manage.py migrate`.
