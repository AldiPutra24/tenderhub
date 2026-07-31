# GPFE PROC HUB Data Source Workflow

Dokumen ini menjelaskan workflow data tender GPFE PROC HUB.

## Prioritas Data Source

Primary operational source: **SPSE via `scrape_spse_live`**

Dipakai untuk:

- Tender Explorer
- Dashboard tender aktif
- Bookmark
- Watchlist LPSE
- Notification tender baru
- AI Match
- Detail tender
- Link `Buka di LPSE`

Secondary analytics source: **INAPROC Realisasi CSV**

Dipakai untuk:

- Analytics realisasi
- Penyedia pemenang
- Competitor Insight
- Vendor Directory
- Nilai realisasi/kontrak
- Data penyedia pemenang

Warning:

- VPS/datacenter sering terkena `403 Forbidden`, Cloudflare, atau PerimeterX
  saat akses SPSE/INAPROC.
- Scrape utama disarankan dari lokal atau IP yang bisa membuka
  `https://spse.inaproc.id`.
- VPS cukup dipakai untuk aplikasi, dashboard, migrasi, dan import file hasil
  scrape lokal.
- Jangan hapus data tender di VPS sebelum import ulang. Gunakan upsert.

## Source Utama: SPSE `scrape_spse_live`

List scrape semua slug:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5
```

List scrape satu slug:

```bash
python manage.py scrape_spse_live --slug jakarta --tahun 2026 --sleep-min 2 --sleep-max 5
```

Detail enrichment semua slug:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --missing-detail-only --sleep-min 2 --sleep-max 5
```

Detail satu kode:

```bash
python manage.py scrape_spse_live --kode-tender 10139423000 --slug polri --enrich-detail
```

Filter status list:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --list-status OPEN,ONGOING
```

Filter detail:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --missing-detail-only --detail-status OPEN,ONGOING
```

Status operasional SPSE:

```text
OPEN
ONGOING
FINISH
FAILED
```

Tahapan yang mengandung kata `batal` atau `gagal` dinormalisasi menjadi
`FAILED`. Tender aktif adalah `OPEN` + `ONGOING`.

## Export/Import SPSE Lokal ke VPS

Lokal scrape:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5
```

Lokal export:

```powershell
python -X utf8 manage.py dumpdata tenders.Tender --indent 2 --output spse_tenders.json
```

Upload ke VPS:

```bash
scp spse_tenders.json root@VPS:/var/www/tenderhub/
```

VPS:

```bash
python manage.py migrate
python manage.py import_spse_tenders_file spse_tenders.json
```

Untuk file besar, command import menampilkan progress dan memakai batch write.
Jika ingin progress lebih sering:

```bash
python manage.py import_spse_tenders_file spse_tenders.json --progress-every 500 --batch-size 1000
```

Untuk testing import tanpa menulis database:

```bash
python manage.py import_spse_tenders_file spse_tenders.json --dry-run --limit 10
```

`loaddata` tetap bisa dipakai untuk import awal/restore ketika database cocok
dengan fixture, tetapi untuk sync rutin gunakan `import_spse_tenders_file`
karena command ini mengabaikan primary key lokal, upsert berdasarkan
`kode_tender + lpse_slug`, dan tidak menghapus bookmark atau relasi user.

## Source Secondary: INAPROC Realisasi CSV

Import paket berlangsung tahun berjalan:

```bash
python manage.py import_realisasi --tahun 2026 --status BERLANGSUNG
```

Import paket selesai:

```bash
python manage.py import_realisasi --tahun 2026 --status SELESAI
```

Import semua status valid:

```bash
python manage.py import_realisasi --tahun 2026 --all-status
```

Catatan: halaman tabel bisa dibuka hanya dengan tahun, tetapi export CSV INAPROC
wajib memakai `jenisKlpd` dan `instansi`. Jalankan discovery dulu untuk melihat
kode instansi:

```bash
python manage.py discover_inaproc_instansi
```

Jika VPS kena 403 Cloudflare, discovery bisa dicoba lewat browser headless:

```bash
python manage.py discover_inaproc_instansi --browser-fallback
```

Playwright tidak wajib untuk jalur normal. Jika fallback browser dibutuhkan,
install dependency berikut di environment yang menjalankan command:

```bash
pip install playwright
python -m playwright install chromium
python -m playwright install-deps chromium
```

Fallback paling aman adalah discovery di lokal lalu import JSON di VPS:

```bash
python manage.py discover_inaproc_instansi --export-json inaproc_instansi_2026.json
python manage.py import_inaproc_instansi_json inaproc_instansi_2026.json
```

Contoh import satu instansi:

```bash
python manage.py import_realisasi --tahun 2026 --jenis-klpd 1 --instansi K3 --status BERLANGSUNG
```

Kode `jenisKlpd`:

- `1`: Kementerian
- `2`: Lembaga
- `3`: Provinsi
- `4`: Kabupaten
- `5`: Kota

Import semua instansi aktif hasil discovery:

```bash
python manage.py import_realisasi_all --tahun 2026
```

Testing terbatas:

```bash
python manage.py import_realisasi_all --tahun 2026 --limit-instansi 3 --limit-row 10
```

Jika VPS diblokir saat export CSV, download CSV di lokal, upload ke VPS, lalu
import file manual:

```bash
python manage.py import_realisasi_file path/to/file.csv --tahun 2026 --jenis-klpd 1 --instansi K3 --status BERLANGSUNG
```

Testing tanpa menulis database:

```bash
python manage.py import_realisasi --tahun 2026 --limit 25 --dry-run
```

Jika endpoint mengembalikan 403, aktifkan debug HTTP aman:

```bash
python manage.py import_realisasi --tahun 2026 --limit 5 --debug-http
```

Jika requests tetap terkena 403 karena Cloudflare/session browser, fallback Playwright
tersedia secara opsional:

```bash
python manage.py import_realisasi --tahun 2026 --status BERLANGSUNG --limit 5 --browser-fallback
```

Fallback ini tidak menjadi default. Jika Playwright belum tersedia di environment,
install dulu:

```bash
pip install playwright
python -m playwright install chromium
```

Filter yang tersedia:

```bash
python manage.py import_realisasi \
  --tahun 2026 \
  --status BERLANGSUNG \
  --instansi "Kementerian Pekerjaan Umum" \
  --jenis-klpd "Kementerian" \
  --search-paket "jalan" \
  --search-penyedia "nama vendor"
```

Detail enrichment Realisasi bersifat experimental/low priority. Gunakan hanya
jika memang membutuhkan data tambahan Realisasi, bukan sebagai proses utama
Tender Explorer.

Detail enrichment untuk data yang masih belum memiliki `nilai_hps`,
`nilai_pagu`, `lokasi_pekerjaan`, atau `detail_url`:

```bash
python manage.py enrich_realisasi_detail --tahun 2026 --limit 100
```

Satu kode paket/tender:

```bash
python manage.py enrich_realisasi_detail --kode 10123076000
```

Scheduler Realisasi yang disarankan untuk analytics:

- `import_realisasi --status BERLANGSUNG` setiap 30 menit
- `import_realisasi --status SELESAI` satu kali per hari
- `enrich_realisasi_detail` opsional/experimental jika data detail Realisasi
  memang dibutuhkan

## Prinsip Utama

- Gunakan SPSE `scrape_spse_live` untuk sync operasional utama.
- Gunakan endpoint CSV INAPROC Realisasi untuk analytics dan competitor insight.
- Scraping SPSE dijalankan dari mesin lokal atau IP yang bisa membuka `https://spse.inaproc.id`.
- VPS dipakai untuk menjalankan aplikasi, dashboard, dan import data.
- Jangan hapus data tender di VPS sebelum import ulang.
- Untuk sync SPSE berulang, gunakan pola upsert berdasarkan `kode_tender + lpse_slug`
  dengan fallback `kode_tender`, bukan replace database.
- Untuk sync Realisasi berulang, gunakan `kode_paket` dengan fallback `kode_tender`.
- LKPP ISB API sync tetap bisa dijalankan langsung di VPS karena endpoint-nya resmi dan lebih stabil.

## Kenapa Scrape Dari Lokal

SPSE INAPROC dapat mengembalikan `403 Forbidden` untuk IP VPS/datacenter. Jika GET halaman list seperti ini sudah gagal:

```text
https://spse.inaproc.id/{slug}/lelang?kategoriId=&tahun=2026&instansiId=&rekanan=&kontrak_status=&kontrak_tipe=
```

maka endpoint DataTables juga tidak bisa dipakai karena scraper perlu mengambil `authenticityToken` dari halaman list terlebih dahulu.

Karena itu workflow yang disarankan:

1. Scrape data di lokal.
2. Export hasil scrape.
3. Upload file export ke VPS.
4. Import/update data di VPS.

## Tahap 1: Scrape List Tanpa Detail

Jalankan dari lokal:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026
```

Command ini akan:

- menyinkronkan slug terbaru dari portal `https://spse.inaproc.id/` ke `tenders/data/lpse_slug_mapping.json`
- membaca semua slug dari `tenders/data/lpse_slug_mapping.json`
- mengambil data list DataTables SPSE
- menyimpan `kode_tender`, `nama_paket`, `instansi`, `klpd_instansi`, `tahapan`, `status`, `nilai_hps`, `jenis_pengadaan`, `tahun_anggaran`, `lpse_slug`, `lpse_name`, dan URL detail
- mendeteksi badge `Tender Ulang` dari list SPSE dan menyimpan `tender_ulang`
- tidak mengambil halaman detail tender

Refresh slug otomatis hanya berjalan untuk `--all-slugs`. Jika ingin mengecek tanpa mengubah file:

```bash
python manage.py sync_spse_slugs --dry-run --show-changes
```

Jika ingin scrape memakai file lokal tanpa refresh:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --no-refresh-slugs
```

Jika ingin menjalankan scrape list lalu langsung lanjut detail enrichment untuk tender aktif yang detailnya masih kurang:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5 --then-detail-only --missing-detail-only --detail-status OPEN,ONGOING
```

Untuk satu LPSE saja:

```bash
python manage.py scrape_spse_live --slug jakarta --tahun 2026
```

### Filter List Berdasarkan Status

List scrape tanpa detail juga bisa difilter berdasarkan status hasil normalisasi tahapan.

Contoh hanya status `OPEN`:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --list-status OPEN
```

Contoh beberapa status:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --list-status OPEN,ONGOING
```

Jika ingin semua status, tidak perlu menambahkan flag karena default-nya mengambil semuanya:

```text
OPEN
ONGOING
FINISH
FAILED
```

## Tahap 2: Enrich Detail Semua Slug

Setelah tahap list selesai, jalankan detail enrichment:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only
```

Command ini akan:

- mencari tender existing berdasarkan `lpse_slug`, `detail_url`, atau `lpse_detail_url`
- mencocokkan `--tahun` terhadap seluruh tahun pada tender multi-tahun, bukan hanya satu tahun terakhir
- membuka halaman detail SPSE
- memperbarui field detail seperti `tanggal_pembuatan`, `sumber_dana`, `lokasi_pekerjaan`, `satuankerja`, `nilai_pagu`, `nilai_hps`, `peserta_count`, dan `tahapan`
- mengambil alasan tender ulang dari label detail `Alasan di ulang` jika tersedia

Tender multi-tahun disimpan dalam format seperti `2026, 2027, 2028`. Untuk
data lama yang sebelumnya hanya tersimpan sebagai tahun terakhir, command
detail akan mencoba recovery satu kali jika field detail tender masih kosong.

Untuk satu LPSE:

```bash
python manage.py scrape_spse_live --slug jakarta --tahun 2026 --detail-only
```

Untuk satu kode tender:

```bash
python manage.py scrape_spse_live --kode-tender 10139423000 --slug polri --enrich-detail
```

### Enrich Detail Yang Masih Kosong Saja

Secara default, `--detail-only` akan mencoba membuka ulang detail tender yang match filter.

Jika hanya ingin scrape tender yang detailnya masih kosong, tambahkan:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --missing-detail-only
```

Untuk satu LPSE:

```bash
python manage.py scrape_spse_live --slug jakarta --tahun 2026 --detail-only --missing-detail-only
```

Field yang dianggap indikator detail masih kosong:

- `tanggal_pembuatan`
- `lokasi_pekerjaan`
- `sumber_dana`
- `satuankerja`
- `nilai_pagu`
- `peserta_count`

Flag ini juga bisa digabung dengan filter status:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --missing-detail-only --detail-status OPEN,ONGOING
```

## Tender Ulang

Tender ulang diproses dari dua sumber:

- list SPSE: badge HTML `Tender Ulang` pada nama paket
- detail SPSE: baris `Alasan di ulang`

Contoh HTML detail:

```html
<tr>
    <th class="bgwarning">Alasan di ulang</th>
    <td colspan="3">-Tidak ada peserta yang menyampaikan dokumen penawaran setelah ada pemberian waktu perpanjangan</td>
</tr>
```

Field yang diisi:

- `tender_ulang = True`
- `alasan_ulang`

Untuk mengisi ulang data tender ulang dari list:

```bash
python manage.py scrape_spse_live --slug polri --tahun 2026
```

Untuk mengambil alasan ulang dari detail:

```bash
python manage.py scrape_spse_live --slug polri --tahun 2026 --detail-only
```

## Filter Detail Berdasarkan Status

Gunakan `--detail-status` jika hanya ingin enrich status tertentu.

Contoh hanya tender aktif/open:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --detail-status OPEN
```

Contoh open dan ongoing:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --detail-status OPEN,ONGOING
```

Status yang valid:

```text
OPEN
ONGOING
FINISH
FAILED
```

Tahapan SPSE yang mengandung kata `batal` atau `gagal`, termasuk
`Seleksi Batal`, `Tender Batal`, `Seleksi Gagal`, dan `Tender Gagal`,
dinormalisasi menjadi status `FAILED`.

## Reliability: PostgreSQL Neon dan Reconnect

Command `scrape_spse_live` aman dijalankan berjam-jam (3–6 jam) di atas
PostgreSQL Neon. Neon/proxy pool bisa menutup koneksi idle, sehingga
koneksi lama bisa mati di tengah proses.

Penanganan:

- Setiap operasi database dibungkus retry khusus error koneksi:
  - `InterfaceError` dan `OperationalError` → koneksi mati, otomatis
    reconnect (`connection.close()` + `close_old_connections()`) lalu retry.
  - `IntegrityError`, `DataError`, `ProgrammingError` → error logika, TIDAK
    di-retry agar tidak menutupi bug.
- Maksimal 3 retry dengan exponential backoff:
  - retry 1 = 1 detik
  - retry 2 = 2 detik
  - retry 3 = 4 detik
  - plus jitter acak 0–500 ms.
- `close_old_connections()` dipanggil sebelum setiap batch page/slug agar
  socket yang sudah mati dibuang, tidak meracuni row berikutnya.
- `CONN_HEALTH_CHECKS` aktif otomatis ketika `DATABASE_URL` dipakai
  (PostgreSQL). Django akan ping koneksi pooled dan membuang yang mati.
- Jika satu row tetap gagal setelah retry, hanya row itu yang dihitung
  `failed`; slug dan row berikutnya tetap jalan.

## Checkpoint dan Resume

Scraper menyimpan progress ke file JSON:

```text
cache/scrape_progress.json
```

Checkpoint berisi:

- `mode`: `list`, `detail-only`, atau `then-detail-only`
- `tahun`
- `slugs`: daftar slug yang diproses
- `phase`: `list` / `detail` / `done`
- `last_slug`: slug terakhir yang selesai
- `updated_at`: timestamp

Checkpoint ditulis secara atomik (file `.tmp` lalu rename) dan di-flush ke
disk SETELAH SETIAP slug selesai. Aman jika listrik mati atau Ctrl+C.

### Melanjutkan Scrape yang Terhenti

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5 --then-detail-only --missing-detail-only --detail-status OPEN,ONGOING --resume
```

Saat startup dengan `--resume`, scraper menampilkan:

```text
Progress: 351/599
Resume from: halmaheraselatankab
```

Dan melanjutkan dari slug setelah checkpoint terakhir.

- Untuk mode `then-detail-only` yang terhenti di phase `detail`, resume
  otomatis melewati phase list dan langsung lanjut detail.
- Jika checkpoint tidak cocok dengan `mode`/`tahun`/daftar slug, scraper
  memulai dari awal dengan peringatan.

### Mulai Ulang dari Nol

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5 --then-detail-only --missing-detail-only --detail-status OPEN,ONGOING --reset-progress
```

Menghapus checkpoint dan memulai dari slug pertama.

### Interupsi dengan Ctrl+C

Saat `Ctrl+C` ditekan:

- checkpoint terakhir di-flush ke disk
- ditampilkan:

```text
Progress saved. Resume using --resume
```

- command keluar bersih tanpa traceback. Jalankan lagi dengan `--resume`
  untuk melanjutkan dari posisi terakhir.

Catatan: checkpoint/resume hanya berlaku untuk mode `--all-slugs`.
Mode `--slug <satu>` atau `--kode-tender` tetap jalan tanpa checkpoint.

## Pengaturan Sleep

Untuk scraping yang lebih pelan dan stabil:

```bash
python manage.py scrape_spse_live --all-slugs --tahun 2026 --sleep-min 2 --sleep-max 5
python manage.py scrape_spse_live --all-slugs --tahun 2026 --detail-only --sleep-min 2 --sleep-max 5
```

Hindari scraping terlalu agresif seperti `--sleep-min 0` untuk semua slug.

## Scrape Detail Dari File Slug

Jika punya file `slug-undone.md` berisi 1 slug per baris, jalankan dari PowerShell lokal:

```powershell
Get-Content .\slug-undone.md |
  Where-Object { $_.Trim() -ne "" } |
  ForEach-Object {
    $slug = $_.Trim()
    Write-Host "DETAIL START slug=$slug" -ForegroundColor Cyan

    .\venv\Scripts\python.exe manage.py scrape_spse_live `
      --slug $slug `
      --tahun 2026 `
      --detail-only `
      --missing-detail-only `
      --sleep-min 2 `
      --sleep-max 5

    if ($LASTEXITCODE -eq 0) {
      Add-Content .\slug-detail-done-today.md $slug
      Write-Host "DETAIL DONE slug=$slug" -ForegroundColor Green
    } else {
      Add-Content .\slug-detail-failed-today.md $slug
      Write-Host "DETAIL FAILED slug=$slug" -ForegroundColor Red
    }
  }
```

Dengan filter status:

```powershell
Get-Content .\slug-undone.md |
  Where-Object { $_.Trim() -ne "" } |
  ForEach-Object {
    $slug = $_.Trim()
    .\venv\Scripts\python.exe manage.py scrape_spse_live `
      --slug $slug `
      --tahun 2026 `
      --detail-only `
      --missing-detail-only `
      --detail-status OPEN,ONGOING `
      --sleep-min 2 `
      --sleep-max 5
  }
```

## Export Data Dari Lokal

Untuk export seluruh data tender:

```bash
python manage.py dumpdata tenders.Tender --indent 2 --output spse_tenders.json
```

Di Windows, gunakan Python UTF-8 mode agar karakter seperti zero-width space tidak membuat `dumpdata` gagal:

```powershell
python -X utf8 manage.py dumpdata tenders.Tender --indent 2 --output spse_tenders.json
```

Gunakan `--output`, bukan redirect `>`, terutama di Windows PowerShell. Redirect PowerShell bisa membuat file UTF-16 sehingga `loaddata` di Linux gagal dengan error seperti:

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0
```

Catatan: `dumpdata` membawa primary key dari database lokal. Ini praktis untuk backup atau import awal, tetapi kurang ideal untuk sync rutin ke VPS yang sudah punya data produksi.

Compress file:

```bash
tar -czf spse_tenders.tar.gz spse_tenders.json
```

Di Windows PowerShell bisa pakai:

```powershell
Compress-Archive -Path spse_tenders.json -DestinationPath spse_tenders.zip -Force
```

## Upload Ke VPS

Contoh upload dengan `scp`:

```bash
scp spse_tenders.tar.gz root@IP_VPS:/var/www/tenderhub/
```

Jika memakai zip:

```bash
scp spse_tenders.zip root@IP_VPS:/var/www/tenderhub/
```

## Import Di VPS

Masuk ke project:

```bash
cd /var/www/tenderhub
source .venv/bin/activate
```

Setelah pull perubahan model, jalankan migrasi:

```bash
python manage.py migrate
```

Ini penting karena beberapa field SPSE bisa panjang. Contohnya `satuankerja` dapat berisi banyak satker sekaligus, sehingga kolom database harus sudah dimigrasikan menjadi `TextField`. Jika belum migrasi, `loaddata` di PostgreSQL bisa gagal dengan:

```text
value too long for type character varying(255)
```

Backup data VPS sebelum import:

```bash
python manage.py dumpdata tenders.Tender --indent 2 --output backup_tenders_before_import.json
```

Extract file:

```bash
tar -xzf spse_tenders.tar.gz
```

Import:

```bash
python manage.py loaddata spse_tenders.json
```

Jika muncul error UTF-8 seperti `byte 0xff in position 0`, berarti file JSON kemungkinan UTF-16. Konversi di VPS:

```bash
python - <<'PY'
from pathlib import Path
path = Path("spse_tenders.json")
raw = path.read_bytes()
if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
    text = raw.decode("utf-16")
    path.write_text(text, encoding="utf-8")
    print("Converted spse_tenders.json from UTF-16 to UTF-8")
else:
    print("spse_tenders.json is not UTF-16 BOM; no conversion needed")
PY
```

Lalu ulangi:

```bash
python manage.py loaddata spse_tenders.json
```

Gunakan `loaddata` hanya jika kondisi database VPS memang cocok dengan file
fixture lokal, misalnya import awal atau restore backup. Untuk import rutin
SPSE, lebih aman gunakan:

```bash
python manage.py import_spse_tenders_file spse_tenders.json
```

Verifikasi:

```bash
python manage.py check
python manage.py shell -c "from tenders.models import Tender; print(Tender.objects.exclude(lpse_slug='').count(), Tender.objects.exclude(detail_url='').count())"
```

## Catatan Penting Tentang Import Berulang

Jangan hapus data VPS sebelum import ulang.

Namun, `loaddata` tidak ideal untuk import rutin karena bekerja dengan primary key dari database lokal. Jika ID lokal dan ID VPS berbeda, import bisa bentrok atau overwrite record yang tidak diinginkan.

Untuk import SPSE berulang, pendekatan terbaik adalah command import khusus
yang melakukan lookup berdasarkan `kode_tender + lpse_slug` jika slug tersedia,
dengan fallback `kode_tender`:

```python
Tender.objects.update_or_create(
    kode_tender=kode_tender,
    lpse_slug=lpse_slug,
    defaults=payload,
)
```

Untuk import Realisasi berulang, gunakan `kode_paket` dengan fallback
`kode_tender`.

Dengan pendekatan ini:

- tender yang sudah ada akan di-update
- tender baru akan dibuat
- data lama yang tidak ada di file import tetap aman
- bookmark dan relasi user di VPS tidak perlu dihapus
- primary key VPS tetap dipertahankan

## LKPP ISB API Di VPS

Untuk data resmi LKPP, command ini bisa dijalankan langsung di VPS:

```bash
python manage.py sync_lkpp_api --tahun 2026 --all-lpse
```

Atau bertahap:

```bash
python manage.py sync_lkpp_api --tahun 2026 --limit-lpse 50
```

## Troubleshooting

Jika SPSE mengembalikan `403 Forbidden` di VPS:

- jangan paksa scraping dari VPS
- jalankan scraping dari lokal atau IP yang bisa membuka SPSE
- import hasilnya ke VPS

Jika tombol `Buka di LPSE` tidak muncul di VPS, cek apakah data SPSE sudah terimport:

```bash
python manage.py shell -c "from tenders.models import Tender; print(Tender.objects.exclude(detail_url='').count(), Tender.objects.exclude(lpse_detail_url='').count(), Tender.objects.exclude(lpse_slug='').count())"
```

Jika semua `0`, berarti VPS belum punya data SPSE/detail URL. Import data hasil scrape lokal terlebih dahulu.

Jika badge `Tender Ulang` belum muncul pada data lama, jalankan ulang list scrape untuk slug terkait:

```bash
python manage.py scrape_spse_live --slug polri --tahun 2026
```

Jika `Alasan Ulang` belum muncul, jalankan detail enrichment:

```bash
python manage.py scrape_spse_live --slug polri --tahun 2026 --detail-only --missing-detail-only
```
