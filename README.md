# QUANT FOUNDS — نظام تحليل تداول كمّي متعدد المحركات

الهيكل الأولي (Skeleton) لمشروع **QUANT FOUNDS** بلغة بايثون، مبني حسب وثيقة المخطط (Blueprint) الإصدار 1.0. المشروع يعتمد على **مكتبة بايثون القياسية فقط** (بدون أي اعتماديات خارجية).

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

## التقييم وآلة الحالة (المخطط §5)

الأوزان: الاتجاه 15 + البنية 15 + السيولة 20 + تدفق الأوامر 15 + الزخم/التقلب 10 + MTF 10 + السياق 5 + R:R 10 = **100**.

مسار الإشارة: `WATCH → SETUP → CONFIRMED → ENTRY_READY → ACTIVE → EXITED` (أو `INVALIDATED/EXPIRED`). أي فلتر اتفاق صعب (Hard Failure) يمنع القرار فوراً مع تسجيل السبب.

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
- ✔ المراحل 1–7: المحركات التحليلية، طبقة القرار، المخاطر، التنفيذ، الجلسات، الفلاتر، لوحة العرض، التنبيهات، والتقييم الإحصائي.
- ✔ الاختبارات: 34 اختباراً (وحدات + smoke) تشمل: جودة البيانات، أولوية SL في الشموع الملتبسة، حد الخسارة اليومي، Kill-Switch، عدم وجود قرار قبل فترة التهيئة.
- ○ قادم: ربط بيانات حقيقية (MT5/cTrader/Bridge)، محرك AI عند توفر موديل، واجهات رسومية.

## ملاحظات مهمة

- نظام **OrderFlow** يعمل حالياً بوضع `ESTIMATED` (تقدير من جسم الشمعة × الحجم) بخصم 0.7 على الدرجة؛ عند توفر دلتا حقيقية يتم تمرير `delta_series` ويُلغى الخصم.
- وسيط الورق يحاكي السبريد والانزلاق، وقاعدة **SL أولاً عند الملتبسة** تمنع التفاؤل الزائف في الباكتيست.
