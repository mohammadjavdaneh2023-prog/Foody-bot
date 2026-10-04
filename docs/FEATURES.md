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
8. مالک از Status و Recent Logs وضعیت را می‌بیند یا با `/off` همهٔ Profileها را خاموش می‌کند.

## داده‌های دائمی

- Profileها، mode، cooldown و محدودهٔ Human Delay.
- گروه‌های Rule، عبارت‌های normalized و NOT terms.
- Replyها و پنجره‌های Schedule.
- Updateهای پردازش‌شده برای deduplication.
- تاریخ آخرین تماس هر Profile/گیرنده برای cooldown.
- فهرست opt-out گیرندگان.
- صف خروجی، attempt، نتیجه و حالت ambiguous.
- رخدادهای عملیاتی کوتاه‌عمر.

## سرویس‌های خارجی

- Telegram MTProto برای User Client و Control Bot.
- PostgreSQL برای همهٔ داده‌های دائمی.
- Darkube و GitHub فقط در انتشار آینده و پس از اجازهٔ مالک.

AI و فایل دائمی محصول وجود ندارند؛ Gemini، Cloudflare، S3 و providerهای AI در runtime استفاده نمی‌شوند.

## اختلاف مستندات قدیمی با کد قبلی

- سند قدیمی SQLite و Railway را الزام می‌دانست؛ قرارداد جدید PostgreSQL، Docker و Darkube `c23` را الزام می‌کند.
- سند قدیمی صف را حافظه‌ای توصیف می‌کرد؛ این صف restart-safe نبود.
- سند قدیمی health endpoint و migration نسخه‌دار نداشت.
- پیاده‌سازی قبلی Human Delay را داشت، هرچند بخش‌های قدیمی Specification آن را کامل پوشش نمی‌دادند.
- کد واقعی پیش از این تغییرات منبع حفظ رفتار قرار گرفته است.
