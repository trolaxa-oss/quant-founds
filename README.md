# QUANT FOUNDS — نظام تحليل تداول كمّي متعدد المحركات
[![tests](https://github.com/trolaxa-oss/quant-founds/actions/workflows/tests.yml/badge.svg)](https://github.com/trolaxa-oss/quant-founds/actions/workflows/tests.yml) [![Release](https://img.shields.io/badge/release-v1.1.1-blue)](https://github.com/trolaxa-oss/quant-founds/releases)

الهيكل الأولي (Skeleton) لمشروع **QUANT FOUNDS** بلغة بايثون، مبني حسب وثيقة المخطط (Blueprint) الإصدار 1.0. المشروع يعتمد على **مكتبة بايثون القياسية فقط** (بدون أي اعتماديات خارجية).

## التوثيق

- [دليل الاستخدام](docs/USAGE.md) — خطوات التشغيل خطوة بخطوة: أول موقع تجريبي، البيانات الحقيقية، التداول الورقي، الإشعارات، حل المشكلات.
- [سجل التغييرات](CHANGELOG.md) — ما الجديد في كل إصدار.
- [دليل المساهمة](CONTRIBUTING.md) — قواعد المشروع الملزمة وسير عمل الـ PR.
- **المخطط الأصلي** توفر نسخة مصدرية للمخطط خارج المستودع، وتُوثَّق أقسامه (1–19) في هذا الدليل.

## المبادئ الهندسية (المخطط §2)

- **الشفافية**: كل إشارة تحمل أسبابها القابلة للفحص (`evidence`، `components`، `hard_failures`).
- **عدم إعادة الرسم (No-Repaint)**: المحركات ترى المغلقات فقط — `assert_closed_only()` ترفض أي شمعة قيد التكوين، والمحرك الأعلى زمنياً يُسقَط إن لم يكن مغلقاً.
- **فصل المسؤوليات**: محرك البيانات لا يقرر، محرك الإشارات لا ينفّذ، ومحرك المخاطر سلطة نهائية يمكنه الاعتراض (Veto) على أي صفقة.
- **كل شيء من الإعدادات**: الأوزان والعتبات والمخاطر والفلاتر في `config/default.toml` — لا قيم صلبة في الكود.
- **توثيق كامل للقرارات**: كل قرار (بما فيه المرفوض) يُسجّل في `decisions.jsonl`.

## هيكل المشروع

```
quant-founds/
├── quant_founds/
│   ├── core/          # enums, models, config, واجهة المحرك الموحدة (EngineResult)
│   ├── engines/       # المحركات التحليلية 01–10
│   │   ├── data_engine.py        (01) التحقق من البيانات وجودتها
│   │   ├── market_intel.py       (02) الاتجاه والقوة والنظام
│   │   ├── liquidity_intel.py    (04) مستويات BSL/SSL وانسياب السيولة
│   │   ├── orderflow_intel.py    (03) الدلتا التقديرية والامتصاص
│   │   ├── smc_intel.py          (05) BOS/CHOCH/OB/FVG ومناطق Premium/Discount
│   │   ├── mtf_engine.py         (06) توافق الأطر الزمنية
│   │   ├── technical.py          (07) EMA/RSI/MACD/ATR/ADX/Bollinger/VWAP/Supertrend
│   │   ├── news_intel.py         (08) حجب التداول حول الأحداث الاقتصادية
│   │   └── ai_intel.py           (10) اختياري — معطّل افتراضياً
│   ├── decision/      # (11) الفلاتر، التقييم 0–100، آلة حالة الإشارة
│   ├── risk_engine.py # (13) السلطة النهائية: حجم المركز، حدود الخسارة، Kill-Switch
│   ├── execution.py   # (12) وسيط ورقي: SL-first، TP جزئي، BE، Trailing
│   ├── sessions.py    # (14) جلسات آسيا/لندن/نيويورك + فحوصات السلامة
│   ├── decision/filters.py # (15) سلسلة فلترات بأسباب مستقلة
│   ├── quant_stat.py  # (09 + 16) لوحة عرض نصية ولقطة القرار
│   ├── alerts.py      # (17) تنبيهات مع منع التكرار
│   ├── reporting.py   # (18) PF/Expectancy/MDD/Walk-Forward/Monte Carlo
│   ├── journal.py     # (19) سجل القرارات JSONL والصفقات CSV
│   └── backtest.py    # خط الأنابيب الكامل من شمعة إلى صفقة موثقة
├── config/default.toml # كل إعدادات المستخدم (أوزان، مخاطر، جلسات، فلاتر…)
├── scripts/run_backtest.py # تجربة شاملة على بيانات اصطناعية مؤكدة
└── tests/             # 34 اختبار وحدة + smoke للخط الكامل
```

## التشغيل السريع

```bash
# تجربة كاملة (تولّد بيانات اصطناعية EURUSD M15)
python3 scripts/run_backtest.py --seed-data

# الاختبارات
python3 -m unittest discover -s tests
```

المخرجات في `runs/latest/`:
- `decisions.jsonl` — كل قرار بدرجته وتفصيل مكوناته وأسباب رفضه.
- `trades.csv` — الصفقات: الدخول، الحجم، وقف الخسارة، الأهداف، سبب الخروج.
- `summary.json` — تقرير الأداء (Win-rate، Profit Factor، Expectancy، MDD، منحنى الأسهم، تقسيم Walk-Forward) وصدى الإعدادات.

## التشغيل الحي (مراقبة + تداول ورقي — خطط 3، 12، 17)

نفس خط التحليل الكامل يعمل الآن على بيانات حيّة عبر `quant_founds/runtime.py` مع شرطين ثابتين: **الشموع المغلقة فقط** ولا أمر حقيقي أبداً.

- **وضع المراقبة** (تحليل + تنبيهات فقط): `LiveWatcher` — يعالج كل شمعة مغلقة جديدة عبر المحركات ثم طبقة القرار، ويسجّل كل قرار في `runs/live/decisions.jsonl`.
- **وضع التداول الورقي** (`--trade`): `LivePaperRunner` — على كل إشارة CONFIRMED يبني خطة تداول (SL من آخر قاع/قمة، مستهدفات 1R/2R/3R)، يقيّمها محرك المخاطر مع حساب ورقي، ثم ينفّذها في بروكر الورق ويدير الصفقة شمعة بشمعة (TP1 جزئي، نقل لستوب التعادل، trailing)، ويكتب `runs/live_paper/trades.csv` عند كل إغلاق صفقة.

```bash
# مراقبة حيّة (تنبيهات فقط)
python3 scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M15

# تداول ورقي كامل على بيانات حيّة
python3 scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M15 --trade

# تجربة سريعة على ملف CSV مرة واحدة
python3 scripts/live_watch.py --provider csv --trade --once --csv data/sample_EURUSD_M15.csv
```

### إشعارات خارجية (اختيارية — عبر متغيرات البيئة فقط)

```bash
export QF_WEBHOOK_URL="https://discord-or-slack-relay/webhook"   # webhook عام JSON
export QF_TELEGRAM_BOT_TOKEN="..."                                # تيليجرام (اختياري)
export QF_TELEGRAM_CHAT_ID="..."
python3 scripts/live_watch.py --trade           # فشل التسليم يُسجَّل ولا يوقف الحلقة
```

بدون متغيرات بيئة يعمل النظام بإشعارات الكونسول فقط، ولا توضع أي أسرار في ملفات الإعداد.

## محرك AI الأونلاين ولوحة المراقبة (خطط 4.9، 18)

- **`--ai`** (اختياري مع `--trade`): نموذج انحدار لوجستي مصغّر (`quant_founds/online_ai.py`) — لا مكتبات خارجية. يتعلّم من نتيجة كل صفقة ورقية مغلقة (ربح=1، خسارة=0) ويُخزَّن في `runs/live_paper/ai_model.json`. حتى 30 يوم تحديث أخذ العينات يبقى عاطلاً؛ بعدها يضيف `ai_prob` لكل قرار ويُسقِط الإشارات ذات احتمال منخفض قبل المخاطر. **محرك المخاطر يبقى السلطة النهائية.**
- **`--dashboard`** (اختياري مع `--trade`): لوحة HTML حيّة على `http://127.0.0.1:8771` فقط (loopback فقط — لا تُعرض على الشبكة): الحساب، الصفقة المفتوحة، منحنى الربح التراكمي SVG، آخر الصفقات والقرارات والمقاييس، وتتحدث تلقائياً كل 30 ثانية.

```bash
python3 scripts/live_watch.py --provider binance --symbol BTCUSDT --timeframe M15 --trade --ai --dashboard
```

## التقويم الاقتصادي والتحقق من الإعدادات (خطط 4.7، 15.2، 17)

- **التقويم الاقتصادي:** ضع ملف CSV (الأعمدة: `timestamp,currency,impact,name`) وحدده في `[news] events_csv` — يعمل تلقائياً في الباكتيسر وفي التشغيل الحي معًا، ويمنع التداول داخل نافذة الخبر وفق `block_minutes_before/after` و`block_impacts`. نموذج جاهز: `data/events_sample.csv`.
- **التحقق من الإعدادات:** `Config.validate()` يفحص المخاطر والعتبات والأوزان (مجموعها 100) والأفريمات — و`from_toml` يرفض أي إعداد غير صالح برسالة واضحة قبل التشغيل.
- **تقارير أغنى (15.2):** التقرير الآن يتضمن `avg_win/avg_loss`, `total_costs`, `sharpe`, `sortino`, **Monte Carlo** لاحتمالات التراجع (p50/p90/p95)، و**Walk-Forward فعّالة** بمقاييس كل نافذة اختبار + مؤشر `stability`.

## التقييم وآلة الحالة (المخطط §5)

الأوزان: الاتجاه 15 + البنية 15 + السيولة 20 + تدفق الأوامر 15 + الزخم/التقلب 10 + MTF 10 + السياق 5 + R:R 10 = **100**.

مسار الإشارة: `WATCH → SETUP → CONFIRMED → ENTRY_READY → ACTIVE → EXITED` (أو `INVALIDATED/EXPIRED`). أي فلتر اتفاق صعب (Hard Failure) يمنع القرار فوراً مع تسجيل السبب.

## ربط بيانات حقيقية (منصات §12)

ثلاثة موفّرين جاهزين بتبديل سطر واحد من الإعدادات:

| الموفّر | الاستخدام | ملاحظات |
|---|---|---|
| `csv` | ملفات OHLCV محلية | الافتراضي — بدون إنترنت |
| `binance` | واجهة API العامة للعملات الرقمية | بدون مفتاح API، stdlib فقط |
| `mt5_bridge` | فوركس عبر MetaTrader5 | يشغّل جسراً محلياً على جهاز فيه MT5 |

```toml
[data]
source_mode = "binance"        # أو "csv" أو "mt5_bridge"
symbol = "BTCUSDT"
timeframe = "M15"
```

```bash
# سحب بيانات حقيقية إلى CSV ثم تشغيل باكتيست عليها
python3 scripts/fetch_data.py --provider binance --symbol BTCUSDT --timeframe M15 --bars 3000
python3 scripts/run_backtest.py --csv data/BTCUSDT_M15.csv

# فوركس: شغّل الجسر على جهازك (حيث MT5 مثبّت) — loopback فقط
python3 scripts/mt5_bridge_server.py            # + QF_BRIDGE_TOKEN اختيارياً
python3 scripts/fetch_data.py --provider mt5_bridge --symbol EURUSD --timeframe M15 --bars 3000
```

قاعدة عدم إعادة الرسم مطبقة على المصدر نفسه: يُسقِط حالاً أي شمعة غير مغلقة.

## الاستخدام كمرجع برمجي

```python
from quant_founds.core.config import Config
from quant_founds.engines.data_engine import load_csv_ohlcv
from quant_founds.backtest import Backtester

cfg = Config.from_toml("config/default.toml")
candles = load_csv_ohlcv("data/EURUSD_M15.csv")
result = Backtester(cfg, run_dir="runs/latest").run(candles, htf_series={"H1": [...]})
print(result.report["win_rate"], result.report["profit_factor"])
```

## حالة التنفيذ (مخطط المراحل §14)

- ✔ المرحلة 0: هيكل المشروع والواجهة الموحدة والإعدادات.
- ✔ موفّرات البيانات الحقيقية: csv / binance (عام) / جسر MT5 محلي مع مصادقة توكن وعدم تمرير الشموع الحية
- ✔ المراحل 1–7: المحركات التحليلية، طبقة القرار، المخاطر، التنفيذ، الجلسات، الفلاتر، لوحة العرض، التنبيهات، والتقييم الإحصائي.
- ✔ الاختبارات: 85 اختباراً (وحدات + smoke + runtime + AI + لوحة + تقارير وتحقق) تشمل: جودة البيانات، أولوية SL في الشموع الملتبسة، حد الخسارة اليومي، Kill-Switch، عدم وجود قرار قبل فترة التهيئة.
- ✅ التشغيل الحي: حلقة بيانات حيّة + تداول ورقي كامل (قرار ← خطة ← مخاطر ← تنفيذ ← إدارة صفقة) مع سجل قرارات وتنبيهات وإشعارات خارجية اختيارية
- ✅ محرك AI الأونلاين (تعلّم من نتائج الصفقات الورقية + بوابة احتمالية اختيارية) ولوحة مراقبة HTML محلية
- ○ قادم (اختياري): دمج نماذج ML خارجية مدّربة (ONNX/sklearn عند إضافة اعتماديات)،  وواجهات رسومية أعمق.
- ✔ مصدر تقويم اقتصادي API مباشر (Stdlib): `python scripts/fetch_calendar.py --out data/calendar.csv` ثم أشر `news.events_csv` إلى الملف.

## ملاحظات مهمة

- نظام **OrderFlow** يعمل حالياً بوضع `ESTIMATED` (تقدير من جسم الشمعة × الحجم) بخصم 0.7 على الدرجة؛ عند توفر دلتا حقيقية يتم تمرير `delta_series` ويُلغى الخصم.
- وسيط الورق يحاكي السبريد والانزلاق، وقاعدة **SL أولاً عند الملتبسة** تمنع التفاؤل الزائف في الباكتيست.
