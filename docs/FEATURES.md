# FOODY capability baseline

این سند مبنای regression نسخهٔ جدید است و از رفتار کد نسخهٔ قبلی استخراج شده است.

## مسیرهای اصلی کاربر

1. مالک Session، Bot Token، admin ID و target chat جدید را به‌صورت Secret تنظیم می‌کند.
2. مالک در Control Bot با `/start` یا `/menu` وارد منو می‌شود.
3. Profile می‌سازد، Ruleهای AND/OR/NOT، Reply Pool، cooldown، Human Delay و Schedule را تنظیم می‌کند.
4. Profile را `ON` یا `SCHEDULE` می‌کند.
5. Watcher فقط پیام تازهٔ target chat را بررسی می‌کند؛ اولین Profile تطبیق‌یافته انتخاب می‌شود.
6. Update و کار خروجی اتمیک و deduplicated در PostgreSQL ثبت می‌شوند.
7. Sender پس از Human Delay، cooldown و rate limit، DM را ارسال و نتیجه را ثبت می‌کند.
8. پس از موفقیت، متن دقیق DM در پیام خصوصی Control Bot و Saved Messages حساب مالک اعلان می‌شود؛ خطای این اعلان باعث ارسال دوبارهٔ DM نمی‌شود.
9. مالک از Status و Recent Logs وضعیت را می‌بیند یا با `/off` همهٔ Profileها را خاموش می‌کند.

## داده‌های دائمی

- Profileها، mode، cooldown و محدودهٔ Human Delay.
- گروه‌های Rule، عبارت‌های normalized و NOT terms.
- Replyها و پنجره‌های Schedule.
- Updateهای پردازش‌شده برای deduplication.
- تاریخ آخرین تماس هر Profile/گیرنده برای cooldown.
- فهرست opt-out گیرندگان.
- صف خروجی، attempt، نتیجه و حالت ambiguous.
- timestamp آخرین ارسال موفق برای حفظ rate limit سراسری پس از restart.
- رخدادهای عملیاتی کوتاه‌عمر.

## سرویس‌های خارجی

- Telegram MTProto برای User Client و Control Bot.
- اعلان متن DM موفق به Control Bot مالک و Saved Messages حساب مالک.
- PostgreSQL برای همهٔ داده‌های دائمی.
- GitHub Actions برای بررسی تغییرات و Railway برای میزبانی و انتشار.

AI و فایل دائمی محصول وجود ندارند؛ Gemini، Cloudflare، S3 و providerهای AI در runtime استفاده نمی‌شوند.

## اختلاف مستندات قدیمی با کد قبلی

- سند قدیمی SQLite و Railway را الزام می‌دانست؛ نسخهٔ فعلی PostgreSQL و Docker دارد و روی Railway منتشر می‌شود.
- سند قدیمی صف را حافظه‌ای توصیف می‌کرد؛ این صف restart-safe نبود.
- سند قدیمی health endpoint و migration نسخه‌دار نداشت.
- پیاده‌سازی قبلی Human Delay را داشت، هرچند بخش‌های قدیمی Specification آن را کامل پوشش نمی‌دادند.
- کد واقعی پیش از این تغییرات منبع حفظ رفتار قرار گرفته است.
