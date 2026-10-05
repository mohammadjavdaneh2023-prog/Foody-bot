# FOODY

FOODY یک سرویس تک‌نسخه‌ای و همیشه‌روشن برای پایش پیام‌های جدید یک گفت‌وگوی Telegram است. پیام‌ها با Ruleهای قطعی `AND / OR / NOT` تطبیق داده می‌شوند و در صورت Match، یک پاسخ از اکانت شخصی مالک برای فرستنده ارسال می‌شود. تنظیمات محصول فقط از طریق Control Bot خصوصی در دسترس مالک است.

نام محصول: **FOODY**

slug فنی: **`foody`**

## قابلیت‌های فعلی

- پایش فقط پیام‌های جدید یک chat مشخص؛ تاریخچهٔ قبلی پردازش نمی‌شود.
- چند Profile با حالت‌های `OFF`، `ON` و `SCHEDULE`.
- Ruleهای چندگروهی: داخل هر گروه OR و بین گروه‌ها AND؛ NOT سراسری هر Profile.
- نرمال‌سازی حروف فارسی، فاصله‌ها و نیم‌فاصله.
- بازه‌های زمانی روزانه با timezone قابل‌تنظیم.
- Reply Pool، cooldown جدا برای هر Profile/گیرنده و حداقل فاصلهٔ سراسری ارسال که زمان آخرین موفقیت آن در PostgreSQL پایدار است.
- پس از هر DM موفق، متن ارسالی به‌صورت خصوصی در Control Bot و Saved Messages حساب مالک اطلاع داده می‌شود.
- Human Delay تصادفی و قابل‌تنظیم بین صفر تا ۳۰۰ ثانیه؛ این قابلیت نباید برای دورزدن ضداسپم یا محدودیت‌های Telegram استفاده شود.
- Control Bot خصوصی برای ساخت، ویرایش و حذف Profile، Rule، زمان‌بندی و Reply.
- دستور `/off` و دکمهٔ All Off برای توقف Matchهای جدید و لغو کارهای ارسال هنوز اجرا‌نشده.
- opt-out پایدار گیرنده با `/stop` در Control Bot و فعال‌سازی دوباره با `/allow`.
- وضعیت سرویس، رخدادهای اخیر و وضعیت صف از Control Bot.
- deduplication Updateها و صف ارسال پایدار در PostgreSQL.
- وضعیت `ambiguous` برای ارسال‌هایی که نتیجه‌شان هنگام قطع process نامعلوم شده است؛ این موارد خودکار تکرار نمی‌شوند.

FOODY قابلیت AI و فایل دائمی ندارد؛ بنابراین BYOK و Object Storage به این نسخه اضافه نشده‌اند.

## معماری

دو کلاینت Telethon در یک process اجرا می‌شوند: User Client برای دیدن گروه و ارسال DM، و Control Bot برای مدیریت. تمام دادهٔ دائمی در PostgreSQL است. migration پیش از Ready شدن اجرا می‌شود و یک advisory lock در PostgreSQL تضمین می‌کند در هر لحظه فقط یک polling consumer فعال باشد.

علاوه بر به‌روزرسانی زندهٔ Telegram، هر ۵ ثانیه پیام‌های بعد از آخرین شناسهٔ دیده‌شده در chat هدف به‌صورت افزایشی بررسی می‌شوند تا تأخیر یا جاافتادن update زنده جبران شود. این کار پیام‌های قدیمی‌تر از شروع سرویس را نخوانده و پردازش هم‌زمان با مسیر زنده به‌کمک کلید یکتای پیام در PostgreSQL تکراری نمی‌شود؛ در عوض، یک درخواست خواندن دوره‌ای اضافه به Telegram ایجاد می‌کند.

صف خروجی قبل از ارسال به وضعیت `sending` می‌رود. موفقیت، رد قطعی Telegram، FloodWait و نتیجهٔ نامعلوم جداگانه ثبت می‌شوند. پس از restart هر کار باقی‌مانده در `sending` به `ambiguous` تبدیل می‌شود و خودکار resend نمی‌شود. timestamp آخرین ارسال موفق در همان transaction نهایی‌شدن کار ثبت می‌شود؛ بنابراین restart فاصلهٔ `MIN_SEND_INTERVAL_SECONDS` را صفر نمی‌کند.

کانتینر stateless است؛ هیچ دیتابیس، Session، log یا فایل کاربری روی filesystem کانتینر نگهداری نمی‌شود.

## پیش‌نیازها

- Docker و Docker Compose برای مسیر پیشنهادی اجرای محلی؛ یا Python `3.12.8` و PostgreSQL `16`.
- API ID و API Hash جدید از `my.telegram.org`.
- StringSession جدید برای اکانت مالک.
- Bot جدید از BotFather و Telegram ID عددی مالک.
- اکانت مالک باید عضو chat هدف باشد و شرایط استفاده و محدودیت‌های Telegram رعایت شوند.

## متغیرهای محیطی

فایل `.env.example` تنها قالب مجاز Repository است. آن را به `.env` کپی کنید و `.env` را هرگز Commit نکنید.

| متغیر | وضعیت | کاربرد |
|---|---|---|
| `APP_ENV` | لازم | محیط اجرا مانند `development` یا `production` |
| `APP_VERSION` | لازم | نسخهٔ release یا Commit |
| `DATABASE_URL` | لازم/Secret | اتصال PostgreSQL اختصاصی محصول |
| `LOG_LEVEL` | اختیاری | سطح log |
| `PORT` | اختیاری | پورت HTTP؛ پیش‌فرض `8080` |
| `DEFAULT_TIMEZONE` | اختیاری | timezone محصول؛ پیش‌فرض `Asia/Tehran` |
| `APP_ENCRYPTION_KEY` | رزروشده | برای Secretهای رمز‌شدهٔ احتمالی آینده؛ در نسخهٔ فعلی مصرف نمی‌شود |
| `TG_API_ID` | لازم | Telegram API ID |
| `TG_API_HASH` | لازم/Secret | Telegram API Hash |
| `TG_STRING_SESSION` | لازم/Secret | StringSession جدید |
| `CONTROL_BOT_TOKEN` | لازم/Secret | Token بات جدید |
| `CONTROL_ADMIN_ID` | لازم | Telegram ID عددی مالک |
| `TARGET_CHAT_ID` | لازم | ID عددی chat هدف |
| `TG_PROXY_URL` | اختیاری/Secret | proxy از نوع HTTP، SOCKS4 یا SOCKS5 |
| `MIN_SEND_INTERVAL_SECONDS` | اختیاری | فاصلهٔ حداقل سراسری ارسال |
| `DEFAULT_USER_COOLDOWN_SECONDS` | اختیاری | cooldown پیش‌فرض Profile جدید |
| `JOB_POLL_INTERVAL_SECONDS` | اختیاری | فاصلهٔ بررسی صف پایدار |
| `POLLER_LOCK_WAIT_SECONDS` | اختیاری | حداکثر انتظار نسخهٔ جدید برای آزادشدن قفل نسخهٔ قبلی؛ پیش‌فرض ۱۲۰ ثانیه |

`DATABASE_URL` باید به دیتابیس و user جداگانهٔ همین محصول با کمترین دسترسی لازم اشاره کند. PostgreSQL server می‌تواند در ابتدا مشترک باشد، اما database، user و password باید مستقل باشند.

## اجرای محلی با Docker

```powershell
Copy-Item .env.example .env
# مقادیر جدید و محلی را در .env وارد کنید
docker compose up --build
```

Compose یک PostgreSQL محلی با volume و یک کانتینر FOODY می‌سازد. برنامه migrationها را خودکار اجرا می‌کند. PostgreSQL خالی است و هیچ import از SQLite قدیمی وجود ندارد.

برای توقف:

```powershell
docker compose down
```

حذف volume محلی تمام داده‌های همان محیط محلی را پاک می‌کند و فقط باید آگاهانه اجرا شود.

## اجرای بدون Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements-dev.txt
Copy-Item .env.example .env
python scripts/migrate.py
python -m app
```

PostgreSQL باید پیشاپیش ساخته شده و `DATABASE_URL` تنظیم شده باشد.

## ساخت Session و یافتن chat

پس از واردکردن `TG_API_ID` و `TG_API_HASH` جدید:

```powershell
python scripts/create_session.py
```

خروجی محرمانه را فقط در Secret میزبان یا `.env` محلی قرار دهید. سپس با `TG_STRING_SESSION` جدید:

```powershell
python scripts/list_dialogs.py
```

این ابزارها با Telegram ارتباط خارجی برقرار می‌کنند و نباید در CI اجرا شوند.

## Migration و دیتابیس خالی

Migrationهای immutable در `migrations/` قرار دارند و checksum آن‌ها در `schema_migrations` ثبت می‌شود. migration اجراشده را ویرایش نکنید؛ برای هر تغییر Schema فایل نسخه‌دار جدید بسازید.

```powershell
python scripts/migrate.py
```

برای بررسی ساخت دیتابیس کاملاً خالی و اجرای idempotent migrationها، فقط روی دیتابیسی که نام آن شامل `test` است:

```powershell
$env:TEST_DATABASE_URL = "postgresql://.../foody_test"
python scripts/verify_migrations.py
```

این فرمان schema دیتابیس تست را پاک می‌کند و هرگز نباید با production اجرا شود.

## تست و کنترل کیفیت

```powershell
ruff check .
ruff format --check .
python -m compileall -q app scripts tests
python scripts/check_repo_clean.py
python -m unittest discover -s tests -v
```

تست integration دیتابیس فقط با `TEST_DATABASE_URL` اجرا می‌شود. تست‌ها هیچ پیام Telegram یا درخواست سرویس خارجی ارسال نمی‌کنند.

GitHub Actions همین بررسی‌ها را با PostgreSQL موقت انجام می‌دهد، migration را از صفر می‌سازد و Docker image را build می‌کند.

## Health Check و نسخه

- `GET /healthz`: زنده‌بودن process؛ پاسخ `200`.
- `GET /readyz`: آماده‌بودن migration، PostgreSQL و هر دو اتصال Telegram؛ در خرابی وابستگی ضروری `503`.
- `GET /version`: مقدار غیرمحرمانهٔ `APP_VERSION`.

پورت پیش‌فرض `8080` است. Ready در شروع migration و هنگام shutdown خاموش است.

در Railway، deployment health check عمداً `/healthz` است، نه `/readyz`. FOODY سرویس HTTP کاربرمحور ندارد؛ این انتخاب اجازه می‌دهد نسخهٔ جدید هنگام انتظار برای advisory lock زنده شناخته شود تا Railway نسخهٔ قبلی را متوقف کند. `/readyz` همچنان معیار واقعی آمادگی عملیاتی است و تا گرفتن قفل و اتصال Telegram پاسخ `503` می‌دهد.

## لاگ و حریم خصوصی

لاگ‌ها JSON و فقط روی stdout نوشته می‌شوند. Token، Session، متن پیام ورودی، Reply خام و خطای خام ارائه‌دهنده نباید log شوند. برای اجرای کار پایدار، متن پیام گروه تا تعیین تکلیف کار خروجی در PostgreSQL باقی می‌ماند و سپس پاک می‌شود. پس از ارسال موفق، متن پیام گروه و Reply بنا به درخواست مالک در پیام خصوصی Control Bot و Saved Messages حساب او فرستاده می‌شوند؛ این اعلان در log یا دیتابیس ذخیره نمی‌شود. رخدادهای عملیاتی محدود در PostgreSQL نگهداری می‌شوند و retention فعلی آن‌ها ۱۴ روز است؛ Updateهای پردازش‌شده پس از ۷ روز پاک می‌شوند.

Control Bot فقط تنظیمات مدیریتی `CONTROL_ADMIN_ID` را می‌پذیرد؛ سایر کاربران فقط می‌توانند با `/stop` انصراف دهند یا با `/allow` انصراف را بردارند. مالک باید مسیر opt-out را به گیرندگان اعلام کند و رضایت و سیاست Telegram را رعایت کند. ارسال ناخواسته، scraping تاریخچه، bulk messaging، دورزدن محدودیت منطقه‌ای/ضداسپم و تقلید فریبندهٔ انسان خارج از دامنه و ممنوع است. Human Delay صرفاً یک تأخیر محصولی قابل‌مشاهده است و مجوز نقض سیاست Telegram نیست.

## بکاپ و Restore

بکاپ باید از محیط مدیریت خارج از کانتینر برنامه اجرا شود و به PostgreSQL همان محصول دسترسی محدود داشته باشد. ابزارها به `pg_dump`/`pg_restore`، `psql` و OpenSSL نیاز دارند.

```sh
export DATABASE_URL='postgresql://.../foody'
export BACKUP_ENCRYPTION_PASSPHRASE='...'
./scripts/backup.sh /secure/staging
```

فایل خروجی با AES-256-CBC، PBKDF2 و permission محدود ساخته می‌شود. پس از تولید، آن را به bucket/prefix اختصاصی FOODY در Object Storage منتقل کنید و نسخهٔ staging محلی را امن حذف کنید. خود برنامه به Object Storage نیاز ندارد؛ این storage فقط برای بکاپ عملیاتی است.

Restore فقط در یک دیتابیس خالی و جداگانه آزمایش شود:

```sh
export DATABASE_URL='postgresql://.../foody_restore_test'
export BACKUP_ENCRYPTION_PASSPHRASE='...'
./scripts/restore.sh /secure/foody-YYYYMMDDTHHMMSSZ.dump.enc
```

سیاست پیشنهادی: ۷ نسخهٔ روزانه، ۵ نسخهٔ هفتگی و ۱۲ نسخهٔ ماهانه. حداقل ماهانه یک Restore آزمایشی انجام و نتیجه ثبت شود. بکاپ production در این Repository یا کانتینر نگهداری نشود و بکاپ میزبان تنها نسخهٔ قابل‌اعتماد فرض نشود.

## Darkube `c23` (گزینهٔ جایگزین)

- منبع build: `Dockerfile` در ریشه.
- Cluster آینده: آلمان، `c23`.
- Replica: دقیقاً `1`.
- Container port و health port: `8080` یا مقدار `PORT` هماهنگ.
- Liveness: `/healthz`؛ Readiness: `/readyz`.
- Start command: همان `CMD` تصویر، یعنی `python -m app`.
- Migration: برنامه پیش از Ready شدن migration را تحت advisory lock اجرا می‌کند؛ اجرای دستی `python scripts/migrate.py` نیز ممکن است.
- PostgreSQL باید خارج از کانتینر برنامه باشد.
- تمام Secretها فقط در کنسول Darkube وارد شوند؛ volume برای برنامه لازم نیست.
- Graceful shutdown حداقل ۳۰ ثانیه فرصت داشته باشد.

این راهنما فقط برای گزینهٔ جایگزین Darkube نگه داشته شده است؛ میزبان عملیاتی فعلی Railway است.

## آماده‌سازی Railway تک‌Replica

فایل `railway.toml` مسیر Docker، health check و teardown را مشخص می‌کند. Railway اعلام کرده Config as Code قدیمی تا `2026-12-01` پشتیبانی می‌شود؛ بنابراین مقادیر Dashboard/Service Variable زیر نیز باید منبع نهایی تنظیمات باشند و در مهاجرت بعدی به Railway IaC منتقل شوند:

- تعداد Replica در Service Settings دقیقاً `1` باشد.
- Health Check Path برابر `/healthz` باشد.
- Deployment Overlap برابر `0` ثانیه باشد.
- Draining Time برابر `30` ثانیه باشد تا نسخهٔ قبلی فرصت دریافت `SIGTERM` و آزادکردن قفل را داشته باشد.
- `POLLER_LOCK_WAIT_SECONDS=120` باقی بماند یا از مجموع build-independent startup و draining بیشتر انتخاب شود.
- PostgreSQL خارج از کانتینر و `DATABASE_URL` از Secretهای Railway باشد.
- volume برای کانتینر برنامه لازم نیست.

ترتیب handoff این است: نسخهٔ جدید `/healthz` را پاسخ می‌دهد و برای advisory lock منتظر می‌ماند؛ Railway با overlap صفر نسخهٔ قبلی را متوقف می‌کند؛ نسخهٔ قبلی در shutdown قفل را آزاد می‌کند؛ نسخهٔ جدید قفل را می‌گیرد، Telegram را متصل می‌کند و سپس `/readyz` به `200` می‌رسد. در این فاصله وقفهٔ کوتاه polling پذیرفته شده است. اگر قفل تا پایان `POLLER_LOCK_WAIT_SECONDS` آزاد نشود، نسخهٔ جدید با خطا خارج می‌شود و restart policy آن را دوباره اجرا می‌کند.

برای سازگاری با تنظیمات Dashboard، این دو Service Variable رسمی Railway نیز باید مقدار متناظر داشته باشند:

```env
RAILWAY_DEPLOYMENT_OVERLAP_SECONDS=0
RAILWAY_DEPLOYMENT_DRAINING_SECONDS=30
```

تنظیمات Dashboard Railway برای مقادیر عملیاتی مرجع هستند. مستندات: [Deployment teardown](https://docs.railway.com/deployments/deployment-teardown) و [Variables reference](https://docs.railway.com/variables/reference).

## GitHub و انتشار آینده

روند موردنظر مالک: Codex تغییر را بررسی و تست می‌کند → پس از اجازهٔ مالک به `main` Push می‌شود → GitHub Actions اجرا می‌شود → Railway با گزینهٔ Wait for CI پس از موفقیت CI خودکار Deploy می‌کند.

Push یا تغییر زیرساخت بدون اجازهٔ مالک انجام نشود. هر تغییر اصلاحی پس از شکست CI باید قبل از Push گزارش و تأیید شود. Force-push انجام نشود. اگر بعداً Ruleset فعال شد، نباید مسیر Push مستقیمِ مورد تأیید مالک و اجرای CI را ناخواسته مسدود کند.

## Rollback

برای rollback کد، image مربوط به آخرین Commit سالم را دوباره منتشر کنید. migrationها رو به جلو و immutable هستند؛ rollback کد نباید migration اعمال‌شده را حذف یا ویرایش کند. اگر نسخهٔ قبلی با Schema جدید سازگار نیست، یک migration اصلاحی جدید بسازید یا بکاپ تأییدشده را در دیتابیس جدا Restore کنید و پس از بررسی مالک، cutover انجام دهید.

## محدودیت‌ها و ریسک‌های باقی‌مانده

- Telegram ارسال دقیقاً-once ارائه نمی‌کند؛ FOODY با ثبت `sending` و توقف retry خودکار، ریسک duplicate را به ریسک نیاز به بررسی دستی تبدیل می‌کند.
- یک وقفهٔ کوتاه هنگام Deploy تک‌Replica پذیرفته شده است.
- Railway از `/healthz` برای handoff استفاده می‌کند؛ بنابراین «Active» شدن deployment اندکی پیش از Ready واقعی Bot رخ می‌دهد و `/readyz` باید جداگانه پایش شود.
- chatهای بسیار پرحجم یا چند target به طراحی worker/partitioning جدید نیاز دارند.
- بازهٔ Schedule عبوری از نیمه‌شب پشتیبانی نمی‌شود.
- Replyهای ساخته‌شده در Control Bot دادهٔ دائمی‌اند؛ دسترسی دیتابیس و بکاپ باید محدود باشد.
- Human Delay بنا به تصمیم محصول حفظ شده و باید مطابق رضایت کاربر و سیاست Telegram استفاده شود.
