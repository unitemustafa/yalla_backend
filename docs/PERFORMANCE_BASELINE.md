# قياس أداء يلا ماركت — دليل التشغيل

الأدوات تقيس خط أساس، ولا تعدّل منطق العمل أو تحسّن الأداء تلقائيًا. نتائج Docker
المحلية تخص موارد الجهاز وDocker Desktop؛ لا تُستخدم لحساب سعة استضافة الإنتاج.
احتفظ بكل المحاولات، بما فيها الفاشلة، تحت معرّف تشغيل واحد وفي مجلدات مستقلة.

## البيئة المعزولة

من جذر `yalla_backend`، باستخدام Python البيئة الافتراضية:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-performance.txt
.venv/Scripts/python.exe tools/performance/bootstrap.py
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml build app
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml up -d postgres redis mail
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml run --rm app python manage.py migrate --noinput
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml run --rm app python manage.py seed_performance
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml up -d app worker media-worker beat nginx
```

اسم المشروع ثابت `yalla-performance`. قاعدة PostgreSQL باسم `yalla_perf`، وشبكة
داخلية وRedis وطوابير وتخزين خاصون به. المنافذ المنشورة على loopback فقط:

| المنفذ | الاستخدام |
|---|---|
| 18080 | Nginx بحد 30 طلب/ثانية و30 اتصالًا لكل IP، مع burst 60 |
| 18081 | مستمع سعة محلي منفصل؛ يتجاوز الحد العام فقط، ويحتفظ بسياسة مصادقة Django |
| 18025 | واجهة مستقبل البريد Mailpit |

ملف الأسرار `.env.local` وملفات الحسابات الخاصة والنتائج مستبعدة من Git ومن
سياق بناء الصورة. لا تُطبع كلمات المرور أو التوكنات. يرفض مولد الحمل أي عنوان
غير loopback أو منفذ غير منفذي القياس، ويرفض أمر البيانات أي إعدادات غير
`config.performance_settings` وقاعدة القياس المعزولة. لا تستخدم ملف staging
الموجود في تطبيق الموبايل قبل مراجعة مضيفه؛ الاسم لا يضمن أنه بيئة اختبار.

التجهيز الافتراضي ينشئ 100 حساب حمل وحسابًا إضافيًا للموبايل، وكتالوجات
100/1000/10000 منتج، وصور WebP بأسماء مختلفة ومحتوى دوري من 64 صورة متنوعة،
وعناوين وطلبات ومفضلة وإشعارات. محتوى الصور صناعي، وليس توزيع صور العملاء.
للحساب الأول ألف طلب تاريخي؛ لباقي الحسابات عشرة. يمنع الأمر إعادة التجهيز
فوق قاعدة تحتوي مستخدمين؛ تجديد التوكنات لا يحتاج مسح البيانات.

لترقية fixture قديمة بها100 حساب فقط، أوقف مولد الحمل أولًا ثم شغل
`seed_performance --reserve-mobile` داخل حاوية app. يضيف الحساب101 وحده
ويحفظ الكتالوجات والطلبات السابقة. لا تشغل الترقية أثناء عملية Locust تكتب
نفس manifest. يرفض أمر الترقية أي قاعدة غير بيئة القياس المعزولة.

البريد يذهب إلى Mailpit. عمال الإشعارات وoutbox يعملون دون تسجيل أجهزة FCM؛
زمن تسليم الإشعارات عبر Firebase خارج الاستنتاجات. إعدادات القياس لا تستورد
ملف `.env` المعتاد، ولا تحتوي مفاتيح مزودي الإنتاج.

## الحمل والمراقبة

```powershell
.venv/Scripts/python.exe tools/performance/run.py --run-id baseline-001 --campaign --route both --smoke-seconds 90
```

بدون `--campaign` ينفذ فحص رحلة بمستخدم واحد فقط. الحملة الكاملة:

1. فحص رحلة حقيقي بحساب واحد، مستقل لكل مسار Nginx.
2. ثلاث جولات من مستويات 10،25،50،100، بمعدل إضافة مستخدمين/ثانية، ودقيقة
   إحماء وخمس دقائق قياس لكل مستوى.
3. ساعة عند أعلى مستوى مستقر مشترك بين الجولات الثلاث، إذا وجد.
4. عملية حمل واحدة مستمرة: نصف المستوى لدقيقتين، المستوى الكامل لدقيقتين،
   ثم نصفه لخمس دقائق للتعافي؛ يحتفظ المستخدمون بجلساتهم عبر الانتقال.

الأوزان 70% تصفح،20% بحث،10% شراء، والفواصل 2–5 ثوان بين خطوات الرحلة.
الأوزان تخص اختيار الرحلة، وليس عدد طلبات HTTP أو عدد المستخدمين الفعلي داخل
كل خطوة. تُقاس طلبات تجديد الجلسة في setup، ويُحسب RPS من الطلبات الفعلية.
`journeys.jsonl` يسجل الرحلات كاملة مع أوقات التفكير، منفصلًا عن أزمنة HTTP؛
لا تُطبق حدود زمن endpoint على زمن الرحلة الذي يضم انتظار المستخدم.
إنشاء الطلب يتحقق من السعر مقارنة بالمعاينة، والقراءة تستخدم `/orders/my/`
كما يفعل العميل؛ مسار `/orders/{id}/` الإداري ليس رحلة عميل. إعادة نفس الطلب
بنفس المفتاح يجب أن تعيد نفس المعرّف. صفحات المنتجات يجب ألا تتكرر وأن تكون
بحد 30 عنصرًا. لا يعيد المولد الطلبات الفاشلة تلقائيًا لإخفاء أخطائها.

تُجمع كل خمس ثوانٍ، مع تسجيل وقت كل عينة: CPU/RAM للمضيف ومولد الحمل وشجرة
عملياته، Docker CPU/الذاكرة، حالات الحاويات وإعادة تشغيلها وOOM، اتصالات وقفل
وdeadlocks PostgreSQL، قراءات الكتل، ذاكرة Redis وإخلاءاته والطوابير، وreadiness.
تُحفظ أزمنة Nginx والـupstream ومعرّف الطلب، وسجلات زمن تنفيذ وانتظار مهام
Celery، دون جسم الطلب أو ترويسات المصادقة. العينات البطيئة نفسها تُظهر فجوات
المراقبة؛ لا تمثل واجهة `monitor.py` التشغيلية بديلًا لتسجيل الحمل.

الإيقاف: readiness يفشل مرتين بفاصل عشر ثوان، ذاكرة المضيف >90% لدقيقة، قرص
المضيف >=85%، أو أخطاء غير متوقعة >5% في نافذة دقيقة. ذاكرة المضيف مشتركة
مع البرامج الأخرى؛ توقفها لا يعني تشبع ذاكرة Django. لا يُرفع الحد لتجاوز
فشل التجربة. 429 يظهر منفصلًا ولا يُسمى خطأ Django. تشبع مولد الحمل يلغي
استنتاج السعة؛ يُسجل احتياج مولد موزع، ولا تشغّل نسخًا تتشارك الحسابات نفسها.

الاستقرار المبدئي: اكتمال الجولة والمراقبة، جميع endpoints المطلوبة ممثلة،
أخطاء غير متوقعة و429 أقل من1% لكل منهما، p95 قراءة <=2ث وإنشاء طلب <=3ث،
ولا OOM/إعادة تشغيل حاوية/زيادة deadlocks/تراكم طوابير متواصل. هذه حدود تقرير
أولية وليست SLA. اجتياز100 يعني اجتياز المستوى المختبر، وليس السعة القصوى.

`requests.jsonl` هو المصدر الأساسي للـpercentiles الدقيقة بطريقة nearest-rank؛
ملفات Locust CSV تحتفظ كذلك بالتاريخ، وقد تقرّب percentiles. لا يُؤخذ متوسط
قيم p95 ولا تُحذف جولة سيئة. ملفات التقرير توضح setup/warmup/measurement/cooldown.

## التشخيص المنفصل

```powershell
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml exec -T app python -m tools.performance.diagnose
.venv/Scripts/python.exe -m unittest tools.performance.test_metrics -v
.venv/Scripts/python.exe manage.py test tools.performance.test_isolation --settings=config.test_settings
```

تشخيص SQL يقارن دفعات المنتج وبيانات المتجر عبر الأحجام الثلاثة، وسجل طلبات
حساب صغير وكبير. يسجل عدد الاستعلامات وزمنها وحجم الرد، وخطط أبطأ ثلاثة
استعلامات SELECT، دون تصدير معاملات SQL. هو فحص in-process منفصل عن HTTP،
ولا يستبدل أزمنة الحمل. لا ينشئ فهارس أو migrations أو يعدل إعدادات الإنتاج.

## الموبايل والتقرير

اتبع دليل `yalla_market/docs/performance-baseline.md`. يجب ربط ملفات الموبايل
والسيرفر ومعرّف التشغيل وإصدارات الكود في التقرير الموحد. النتيجة غير المقاسة
تُسجل بسببها، ولا تُحوّل إلى نجاح. التطبيق المتصل أثناء حمل غير مستقر لا
يستخدم لإعلان تجربة مستقرة تحت100 مستخدم.

عند الانتهاء يمكن إيقاف الخدمات مع الاحتفاظ بالبيانات والنتائج:

```powershell
docker compose --env-file tools/performance/.env.local -f tools/performance/compose.yaml stop
```

المراجع: [Flutter profiling](https://docs.flutter.dev/cookbook/testing/integration/profiling)،
[DevTools memory](https://docs.flutter.dev/tools/devtools/memory)،
[Locust scenarios](https://docs.locust.io/en/stable/writing-a-locustfile.html).

## استخراج التقرير والأدلة

`report.py --help` يعرض مسارات أدلة السيرفر والموبايل والبدء والذاكرة وtrace.
احفظ كل المحاولات السابقة باستخدام `--previous-server` وكرر `--mobile`؛
النتائج غير المكتملة لا تعطي throughput مستدامًا. `timing.json` يحدد نافذة
القياس، ورحلات تعبر بدايتها أو نهايتها تعرض منفصلة بدل تصنيف قطع الرحلة
عند نهاية الاختبار كفشل عمل. checkpoint التقرير يحفظ كل مرحلة فور انتهائها.

Locust يحمّل API فقط ولا يجلب ملفات الصور؛ التصفح المتصل على الهاتف يغطي
مسار الصور وظيفيًا، ولا يثبت سعة الصور مع100 مستخدم. خطط قياس هذه السعة
بمولد أصول منفصل عند توافر موارد كافية.

```powershell
.venv/Scripts/python.exe tools/performance/trace_summary.py TRACE_JSON SPANS_JSON
.venv/Scripts/python.exe tools/performance/report.py --help
```

تظل الأسرار والـheap snapshots وملفات JSON/CSV الخام في مجلدات ignored.
لتنظيف logs التشخيصية الخاصة بهذه الجلسة فقط من تدفقات تطبيقات الهاتف الأخرى
وعناوين VM المؤقتة، مرر ملفات `.log` صراحة إلى `sanitize_logs.py`. لا يغيّر
المنظف ملفات القياس أو يحذف الجولات السيئة.
