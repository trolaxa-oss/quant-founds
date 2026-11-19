# دليل الاستخدام — QUANT FOUNDS

هذا الدليل يجيب على سؤال: «كيف أجرّب المشروع؟» من أول تشغيل حتى التداول الورقي الحي مع الذكاء المتصل ولوحة القيادة.

> تداول ورقي فقط — لا أوامر حقيقية. محرك المخاطرة سلطة نهائية على كل قرار، والشموع المُشكَّلة (غير المغلقة) تُهمل تلقائيًا.

---

## 1. المتطلبات

- Python **3.11** أو أحدث فقط — لا تثبيت أي حزم (مكتبة قياسية 100%).
- لينكس/ماك/ويندوز، الاتصال بالشبكة فقط لمزوّدي Binance أو جسر MT5.

## 2. أول تجربة: تشغيل بيانات اصطناعية (30 ثانية)

```bash
python scripts/run_backtest.py --seed-data
```

هذا يولّد سلسلة اصطناعية حتمية، ويخفض عتبات التقييم ضمن نمط البيانات المبذّرة ليعطي إشارات فعلية، ثم يكتب كل شيء في `runs/latest/`:

| الملف | المحتوى |
|---|---|
| `report.html` | تقرير جولة كامل (افتحه في المتصفح) |
| `summary.json` | مقاييس التشغيل (عدد الصفقات، الربح، السحب، Sharpe/Sortino، Walk-Forward، Monte-Carlo) |
| `trades.csv` | كل الصفقات مع أسعار الدخول/الخروج والأسباب |
| `decisions.jsonl` | كل القرارات بما فيها المرفوضات وأسباب الرفض |

## 3. بيانات حقيقية إلى CSV

### من Binance (بدون مفتاح، Klines عامة)

```bash
python scripts/fetch_data.py --provider binance --symbol BTCUSDT --timeframe M1 --bars 5000 --out data/BTCUSDT_M1.csv
```

### من منصة MT5 عبر الجسر المحلي

شغّل الجسر قرب منصّة MT5 (ويندوز عادةً) مع رمز اختياري:

```bash
QF_BRIDGE_TOKEN=سرّك python scripts/mt5_bridge_server.py --host 127.0.0.1 --port 8770
```

ثم اسحب الشموع:

```bash
QF_BRIDGE_TOKEN=سرّك python scripts/fetch_data.py --provider mt5_bridge --symbol EURUSD --timeframe M15 --bars 5000 --out data/EURUSD_M15.csv
```

الجسر يستمع على **loopback فقط** ولا يفتح أي منفذ خارجي.

## 4. المراقبة الحية (بدون تداول)

```bash
python scripts/live_watch.py --provider csv --csv data/EURUSD_M15.csv --poll 30
# أو مباشرة من Binance:
python scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M1 --poll 30
```

- `--poll` ثواني بين كل فحص لشمعة جديدة.
- في كل شمعة مغلقة تعمل بطارية المحركات، ويطبع النظام مستوى الإشارة الحالي (WATCH/SETUP/...) مع النتيجة من 100.
- اضغط `Ctrl+C` للإيقاف.

اختياريًا: `--config config/examples/mt5_bridge.toml` لتشغيل المراقبة من الجسر نفسه.

## 5. التداول الورقي الكامل (`--trade`)

```bash
python scripts/live_watch.py \
  --provider csv --csv data/EURUSD_M15.csv \
  --trade --balance 10000 \
  --ai --dashboard
```

ماذا يفعل كل خيار:

| الخيار | الوظيفة |
|---|---|
| `--trade` | يفعّل المشغّل الورقي الكامل: حساب + وسيط ورقي + محرك مخاطرة + تنفيذ |
| `--balance 10000` | رصيد البداية |
| `--ai` | يفعّل المتعلّم المتصل `OnlineLogit` كبوابة دخول (لا يُؤثّر قبل بلوغه `ai_min_samples` تحديثًا) |
| `--dashboard` | لوحة قيادة حية على `http://127.0.0.1:8771` (loopback فقط)، تحديث تلقائي كل 30 ثانية |
| `--once` | يعالج شمعة واحدة ويطبع ملخص JSON ثم يخرج (مفيد للاختبارات والمهام المجدولة) |
| `--run-dir runs/live` | مجلد مخرجات مخصّص |

**دورة الحياة في العمل**: `WATCH → SETUP → CONFIRMED → ENTRY_READY → ACTIVE → EXITED/INVALIDATED/EXPIRED`. صفقة واحدة مفتوحة كحد أقصى افتراضيًا (`max_open_positions = 1`)، وبعد كل صفقة مغلقة يُحدَّث نموذج AI من النتيجة ويُحفظ في `run_dir/ai_model.json`.

## 6. الإشعارات (من البيئة فقط — لا أسرار في الملفات)

```bash
export QF_WEBHOOK_URL="https://example.com/hook"          # POST JSON لكل تنبيه
export QF_TELEGRAM_BOT_TOKEN="..."                        # اختياري
export QF_TELEGRAM_CHAT_ID="..."                          # اختياري
python scripts/live_watch.py --provider binance --symbol ETHUSDT --timeframe M5 --trade
```

فشل أي قناة إشعار لا يوقف التشغيل — يُطبع تنبيه على الكونسول ويتابع النظام عمله.

## 7. التقويم الاقتصادي

ضَع ملفًا بأعمدة `timestamp,currency,impact,name` (مثال جاهز: `data/events_sample.csv`) وأشر إليه في الإعدادات — راجع مثال [config/examples/csv_with_news.toml](../config/examples/csv_with_news.toml). يُحجب الدخول داخل نافذة الخبر (`block_minutes_before/after`) للأثر المحدد (`block_impacts`).

أو اسحب التقويم مباشرًا من واجهة عامة بلا مفتاح (Stdlib:
`python scripts/fetch_calendar.py --out data/calendar.csv`) وكرّره أسبوعيًا للتحديث.

## 8. جولات التقييم (Walk-Forward) والسحب (Monte-Carlo)

تُحتسب تلقائيًا في كل تشغيل backtest وتظهر في `summary.json` و`report.html`:

- `walk_forward`: مقاييس فعّالة لكل نافذة زمنية + نسبة استقرار النتائج بين النوافذ.
- `monte_carlo`: توزيع السحب p50/p90/p95 بترتيب عشوائي للصفقات.

## 9. كمكتبة (API)

```python
from quant_founds.core.config import Config
from quant_founds.providers.csv_provider import CsvProvider
from quant_founds.runtime import LiveWatcher

cfg = Config.from_toml("config/default.toml")
watcher = LiveWatcher(provider=CsvProvider(cfg.data.csv_path), cfg=cfg, run_dir="runs/scan")
watcher.process_bar(candle)   # شمعة مغلقة فقط — تخالفها بمظهر SafetyViolation
```

## 10. الاختبارات

```bash
python -m unittest discover -s tests   # 85 اختبارًا (تخطٍ محتمل واحد لمزوّد شبكي)
```

## 11. مشكلات شائعة

| العَرَض | السبب/الحل |
|---|---|
| لا إشارات إطلاقًا | طبيعي على بيانات حقيقية — العتبات الافتراضية 55/70 صارمة. جرّب `--seed-data` أولاً |
| `SafetyViolation: unclosed candles` | مزوّدك يمرّر شموعًا لم تُغلق — هذا الحارس يعمل كما صُمم، استخدم مزوّدًا يطبّق `drop_forming` |
| الإعدادات مرفوضة عند التحميل | `Config.validate()` يشرح الخطأ — صحّح القيم المذكورة (مثال: عتبة خارج 0–100، وزن سالب) |
| لوحة القيادة لا تفتح | تعمل فقط مع `--trade --dashboard`، وعلى `127.0.0.1` فقط — تحقّق من `--port` |
| 429/خطأ شبكي من Binance | أطِل `--poll`، المزوّد عام بلا مفتاح ولديه حدود استخدام |

للمساهمة والقواعد المُلزِمة: [CONTRIBUTING.md](../CONTRIBUTING.md) — وسجلّ التغييرات في [CHANGELOG.md](../CHANGELOG.md).
