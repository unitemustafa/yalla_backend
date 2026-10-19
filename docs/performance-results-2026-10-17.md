# خط أساس أداء يلا ماركت — 2026-10-17

معرف التجربة الجامع: `yalla-baseline-20261017`؛ تحتفظ كل مرحلة بمعرفها وملفاتها الأصلية.

النتائج تخص الجهاز وبيئة Docker المحليين. لا يحدد هذا التقرير سعة الإنتاج، ولا يتضمن تنفيذ تحسينات.

## النتائج العملية وخطوات العلاج

- **تقطيع تغيير الفئات:** تأخر Raster متكرر حتى24.69% من الإطارات في الجولات المصححة، مقابل حد أقل من5%. trace يضع تكلفة GPU Draw/Submit في مقدمة التشخيص. العلاج المقترح: تحديد البطاقة/طبقة الرسم المسؤولة داخل الإطارات البطيئة، ثم تقليل إعادة رسمها وإعادة الجولات نفسها؛ لا يوجد دليل كافٍ الآن لاختيار تعديل widget بعينه.
- **سجل الطلبات الكبير:** نحو2.26MB و2.2ث في تشخيص in-process، مع زمن SQL أقل بكثير. العلاج المقترح: تقسيم سجل الطلبات إلى صفحات وتحميل التفاصيل عند الطلب، بتغيير متوافق بين السيرفر والعميل في مهمة إصلاح مستقلة. هذه فرضية قوية تحتاج مقارنة قبل/بعد، وليست إصلاحًا منفذًا.
- **سعة السيرفر غير محسومة:** نجح smoke بمستخدم واحد، لكن RAM المضيف8GB تجاوزت حد الأمان. الخطوة المطلوبة: فصل مولد الحمل وتوفير موارد اختبار كافية، ثم إعادة10/25/50/100؛ لا يجوز نسبة هذا التوقف إلى تشبع Django.
- **الشراء وبدء التشغيل والذاكرة:** مراجعة شراء Release اجتازت؛30 تشغيلًا باردًا و30 عودة مسجلة؛ جلسة الذاكرة30 دقيقة اكتملت. التفاصيل والحدود أدناه، ومنها أن مراجعة Release ليست30 رحلة لمس وأن صور الكاش والشبكات المضبوطة لم تستكمل.

نسخ الكود والبناء وبصمات ملفات القياس: [sources-and-builds.json](<../tools/performance/artifacts/sources-and-builds.json>).

## الجهاز والمنهج

الجهاز: RMX2061، Android 11، ABI: arm64-v8a,armeabi-v7a,armeabi.
الذاكرة المسجلة: MemTotal:        7776756 kB؛ الوصول: 0؛ لم تغير الأداة إعدادات الجهاز.
دليل الجهاز: [device.json](<../../yalla_market/build/performance/device-20261017/device.json>). قياس الطاقة محدود بسبب شحن USB.

## الواجهة والتفاعل

النسب التالية هي **أسوأ جولة** لكل سيناريو، وليست متوسطًا يخفي الجولات الفاشلة. ميزانية الإطار حسب التردد المسجل؛ الحد أقل من5% لكل من UI وRaster، ولا إطار أكبر من100ms.

### run-20261017-ar-all.raw

النطاق: all؛ اللغة: ar؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: True.
الإدخال: legacy_test_pointer؛ semantics المفروضة بالاختبار: legacy_true.
توثيق الحركة: `legacy_motion_unverified`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `invalid_legacy_profile_text_input`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-ar-all.raw.json](<../../yalla_market/build/performance/run-20261017-ar-all.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| store_100_scroll | 3 | 1664/1664, 1694/1694, 1697/1697 | 1.20 | 0.53 | 55.39 | نعم |
| store_100_category | 3 | 350/350, 361/361, 350/350 | 10.86 | 22.29 | 108.41 | لا |
| store_1000_scroll | 3 | 1569/1569, 1555/1555, 1572/1572 | 3.00 | 2.04 | 52.06 | نعم |
| store_1000_category | 3 | 363/363, 342/342, 346/346 | 11.11 | 24.79 | 141.73 | لا |
| store_10000_scroll | 3 | 1560/1560, 1520/1520, 1558/1558 | 3.55 | 1.97 | 57.47 | نعم |
| store_10000_category | 3 | 348/348, 355/355, 340/340 | 11.21 | 22.35 | 106.79 | لا |
| home_scroll | 3 | 1631/1631, 1641/1641, 1635/1635 | 0.18 | 0.37 | 44.96 | نعم |
| wishlist_scroll | 3 | 1624/1624, 1566/1566, 1576/1576 | 3.74 | 1.59 | 59.60 | نعم |
| notifications_scroll | 3 | 1697/1697, 1689/1689, 1682/1682 | 0.06 | 0.30 | 43.36 | نعم |
| orders_scroll | 3 | 1713/1713, 1688/1688, 1700/1700 | 1.94 | 0.76 | 48.31 | نعم |
| search_scroll | 3 | 1783/1783, 1787/1787, 1792/1792 | 0.00 | 1.46 | 20.63 | نعم |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| store_100_category_us_1 | 20 | 345.74 | 382.11 | 382.31 |
| store_100_category_us_2 | 20 | 334.25 | 374.79 | 383.96 |
| store_100_category_us_3 | 20 | 337.96 | 376.75 | 377.82 |
| store_1000_category_us_1 | 20 | 346.22 | 385.29 | 393.88 |
| store_1000_category_us_2 | 20 | 336.24 | 379.55 | 383.31 |
| store_1000_category_us_3 | 20 | 342.07 | 382.97 | 386.97 |
| store_10000_category_us_1 | 20 | 359.42 | 391.45 | 394.54 |
| store_10000_category_us_2 | 20 | 350.55 | 384.06 | 391.48 |
| store_10000_category_us_3 | 20 | 347.29 | 384.30 | 384.94 |
| search_action_us (غير صالح لزمن البحث) | 30 | 519.28 | 523.07 | 524.30 |
| product_open_us | 30 | 513.94 | 523.23 | 528.22 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-ar-motion-v2.raw

النطاق: all؛ اللغة: ar؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: False.
الإدخال: device؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `verified_motion_v2`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `invalid_legacy_profile_text_input`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-ar-motion-v2.raw.json](<../../yalla_market/build/performance/run-20261017-ar-motion-v2.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| store_100_scroll | 3 | 1775/1775, 1730/1730, 1727/1727 | 3.61 | 0.81 | 91.54 | نعم |
| store_100_category | 3 | 391/391, 420/420, 402/402 | 9.72 | 21.43 | 115.43 | لا |
| store_1000_scroll | 3 | 1732/1732, 1672/1672, 1692/1692 | 4.55 | 1.21 | 48.90 | نعم |
| store_1000_category | 3 | 399/399, 410/410, 412/412 | 9.77 | 21.36 | 111.58 | لا |
| store_10000_scroll | 3 | 1669/1669, 1669/1669, 1730/1730 | 4.57 | 0.78 | 43.26 | نعم |
| store_10000_category | 3 | 395/395, 405/405, 407/407 | 10.13 | 24.69 | 91.11 | لا |
| home_scroll | 3 | 1786/1786, 1779/1779, 1776/1776 | 0.00 | 2.87 | 30.38 | نعم |
| wishlist_scroll | 3 | 1681/1681, 1668/1668, 1751/1751 | 4.62 | 0.40 | 53.38 | نعم |
| notifications_scroll | 3 | 1776/1776, 1792/1792, 1774/1774 | 0.11 | 0.96 | 37.37 | نعم |
| orders_scroll | 3 | 1770/1770, 1755/1755, 1751/1751 | 3.76 | 1.42 | 46.09 | نعم |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| store_100_category_us_1 | 20 | 344.52 | 378.36 | 380.44 |
| store_100_category_us_2 | 20 | 336.96 | 357.66 | 390.81 |
| store_100_category_us_3 | 20 | 340.07 | 360.77 | 365.70 |
| store_1000_category_us_1 | 20 | 339.65 | 344.70 | 393.29 |
| store_1000_category_us_2 | 20 | 338.68 | 359.01 | 369.69 |
| store_1000_category_us_3 | 20 | 338.19 | 359.24 | 360.43 |
| store_10000_category_us_1 | 20 | 339.78 | 378.66 | 383.81 |
| store_10000_category_us_2 | 20 | 339.59 | 369.66 | 374.97 |
| store_10000_category_us_3 | 20 | 341.30 | 367.93 | 384.46 |
| search_action_us (غير صالح لزمن البحث) | 30 | 519.13 | 523.37 | 523.75 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-ar-search-v3.raw

النطاق: search_navigation؛ اللغة: ar؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: True.
الإدخال: device؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `verified_motion_v2`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `verified_profile_text_callback`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-ar-search-v3.raw.json](<../../yalla_market/build/performance/run-20261017-ar-search-v3.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| search_scroll | 3 | 1769/1769, 1831/1831, 1762/1762 | 0.00 | 0.57 | 44.82 | نعم |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| search_action_us | 30 | 519.52 | 622.89 | 623.75 |
| product_open_us | 30 | 511.88 | 516.93 | 519.62 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-ar-store.raw

النطاق: store؛ اللغة: ar؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: False.
الإدخال: legacy_test_pointer؛ semantics المفروضة بالاختبار: legacy_true.
توثيق الحركة: `legacy_motion_unverified`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `not_applicable`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-ar-store.raw.json](<../../yalla_market/build/performance/run-20261017-ar-store.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| store_100_scroll | 3 | 1650/1650, 1834/1834, 1821/1821 | 1.03 | 0.61 | 84.64 | نعم |
| store_100_category | 3 | 409/409, 419/419, 405/405 | 5.93 | 21.48 | 63.65 | لا |
| store_1000_scroll | 3 | 1740/1740, 1727/1727, 1726/1726 | 1.04 | 0.80 | 44.78 | نعم |
| store_1000_category | 3 | 399/399, 408/408, 417/417 | 6.47 | 20.30 | 73.21 | لا |
| store_10000_scroll | 3 | 1759/1759, 1736/1736, 1739/1739 | 0.91 | 1.44 | 52.86 | نعم |
| store_10000_category | 3 | 410/410, 396/396, 396/396 | 7.32 | 25.51 | 76.49 | لا |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| store_100_category_us_1 | 20 | 321.07 | 329.46 | 338.19 |
| store_100_category_us_2 | 20 | 319.65 | 329.51 | 331.57 |
| store_100_category_us_3 | 20 | 319.20 | 330.41 | 331.22 |
| store_1000_category_us_1 | 20 | 320.95 | 328.68 | 336.62 |
| store_1000_category_us_2 | 20 | 321.75 | 340.00 | 342.37 |
| store_1000_category_us_3 | 20 | 321.35 | 334.98 | 338.79 |
| store_10000_category_us_1 | 20 | 323.68 | 335.29 | 339.94 |
| store_10000_category_us_2 | 20 | 320.62 | 335.40 | 337.49 |
| store_10000_category_us_3 | 20 | 320.40 | 328.95 | 335.87 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-category-calibrated.raw

النطاق: category؛ اللغة: ar؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: True.
الإدخال: device؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `not_applicable`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `not_applicable`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-category-calibrated.raw.json](<../../yalla_market/build/performance/run-20261017-category-calibrated.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| store_1000_category | 3 | 420/420, 386/386, 410/410 | 9.84 | 21.43 | 88.01 | لا |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| store_1000_category_us_1 | 20 | 330.27 | 345.79 | 361.86 |
| store_1000_category_us_2 | 20 | 342.57 | 361.05 | 364.50 |
| store_1000_category_us_3 | 20 | 338.17 | 361.47 | 376.67 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-en.raw

النطاق: browse_search؛ اللغة: en؛ المصدر: synthetic_repositories؛ اكتمال السيناريو: True.
الإدخال: device؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `legacy_motion_unverified`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `invalid_legacy_profile_text_input`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-en.raw.json](<../../yalla_market/build/performance/run-20261017-en.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| store_1000_scroll | 3 | 1736/1736, 1734/1734, 1731/1731 | 4.27 | 0.75 | 99.95 | نعم |
| store_1000_category | 3 | 396/396, 399/399, 393/393 | 9.16 | 20.30 | 111.66 | لا |
| search_scroll | 3 | 1839/1839, 1809/1809, 1803/1803 | 0.00 | 8.62 | 28.10 | لا |

| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| store_1000_category_us_1 | 20 | 339.81 | 373.07 | 377.75 |
| store_1000_category_us_2 | 20 | 335.85 | 350.29 | 370.60 |
| store_1000_category_us_3 | 20 | 339.87 | 361.35 | 369.50 |
| search_action_us (غير صالح لزمن البحث) | 30 | 519.12 | 522.50 | 545.62 |

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-offers-residency.raw

النطاق: physical_offers_and_long_list_residency؛ اللغة: None؛ المصدر: None؛ اكتمال السيناريو: False.
الإدخال: legacy_test_pointer؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `not_applicable`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `not_applicable`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-offers-residency.raw.json](<../../yalla_market/build/performance/run-20261017-offers-residency.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|
| offers_page_round | 3 | 1760/1760, 1747/1747, 1794/1794 | 0.61 | 1.09 | 32.44 | نعم |

| القائمة | عناصر مقيمة قبل/بعد | RSS قبل/بعد MiB | كاش الصور بعد bytes |
|---|---|---|---:|
| offers | غير مقاس/غير مقاس | 264.5/294.6 | 2881408 |

العدد هو عناصر حية في الشجرة، وليس مجموع استدعاءات build؛ عينات RSS والكاش وصفية ولا تثبت تسريبًا.

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

### run-20261017-staging-purchase-v2.raw

النطاق: store_ui_checkout_cubit_and_purchase_ui؛ اللغة: ar؛ المصدر: isolated_local_staging؛ اكتمال السيناريو: False.
الإدخال: test؛ semantics المفروضة بالاختبار: False.
توثيق الحركة: `not_applicable`؛ trace تشخيصي: False. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.
صلاحية إدخال البحث: `not_applicable`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.
البيانات الخام: [run-20261017-staging-purchase-v2.raw.json](<../../yalla_market/build/performance/run-20261017-staging-purchase-v2.raw.json>).

| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |
|---|---:|---|---:|---:|---:|---|

هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.
نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.

## السيرفر

الدليل: [report.json](<../tools/performance/artifacts/20261017-resumed-validation/report.json>)، والموارد: [inventory.json](<../tools/performance/artifacts/20261017-resumed-validation/inventory.json>).

| المسار/المرحلة | المستخدمون | طلبات نافذة القياس | أخطاء غير متوقعة | 429 | اكتمال | سبب التوقف |
|---|---:|---:|---:|---:|---|---|
| policy-smoke | 1 | 28 | 0 | 0 | True | — |
| capacity-smoke | 1 | 17 | 0 | 0 | False | host_memory_above_90_percent_for_60s |

أزمنة endpoints مع أحجام العينات؛ الجولة الناقصة لا يُستنتج منها RPS مستدام:

| المرحلة | endpoint | n | p50 ms | p95 ms | p99 ms | RPS صالح | 4xx بدون429 | 429 | 5xx | شبكة | متوسط bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| policy-smoke | store_products | 6 | 129.6 | 153.9 | 153.9 | 0.067 | 0 | 0 | 0 | 0 | 14268 |
| policy-smoke | product_detail | 3 | 45.3 | 59.7 | 59.7 | 0.033 | 0 | 0 | 0 | 0 | 1522 |
| policy-smoke | search | 3 | 124.5 | 143.1 | 143.1 | 0.033 | 0 | 0 | 0 | 0 | 5645 |
| policy-smoke | store_filter | 3 | 141.4 | 360.7 | 360.7 | 0.033 | 0 | 0 | 0 | 0 | 14320 |
| policy-smoke | order_preview | 3 | 44.6 | 44.6 | 44.6 | 0.033 | 0 | 0 | 0 | 0 | 2053 |
| policy-smoke | order_create | 2 | 131.7 | 266.9 | 266.9 | 0.022 | 0 | 0 | 0 | 0 | 3423 |
| policy-smoke | order_detail | 2 | 1653.6 | 1907.6 | 1907.6 | 0.022 | 0 | 0 | 0 | 0 | 2261753 |
| policy-smoke | order_retry | 2 | 39.2 | 49.0 | 49.0 | 0.022 | 0 | 0 | 0 | 0 | 3423 |
| policy-smoke | home | 2 | 120.8 | 135.0 | 135.0 | 0.022 | 0 | 0 | 0 | 0 | 11428 |
| policy-smoke | storefront | 2 | 51.7 | 55.6 | 55.6 | 0.022 | 0 | 0 | 0 | 0 | 944 |
| capacity-smoke | store_products | 3 | 111.3 | 112.9 | 112.9 | — | 0 | 0 | 0 | 0 | 14284 |
| capacity-smoke | product_detail | 2 | 44.7 | 52.0 | 52.0 | — | 0 | 0 | 0 | 0 | 1522 |
| capacity-smoke | search | 2 | 80.8 | 123.8 | 123.8 | — | 0 | 0 | 0 | 0 | 5645 |
| capacity-smoke | store_filter | 2 | 129.1 | 140.1 | 140.1 | — | 0 | 0 | 0 | 0 | 14320 |
| capacity-smoke | order_preview | 2 | 27.4 | 43.7 | 43.7 | — | 0 | 0 | 0 | 0 | 2053 |
| capacity-smoke | order_create | 2 | 108.9 | 116.7 | 116.7 | — | 0 | 0 | 0 | 0 | 3423 |
| capacity-smoke | order_detail | 1 | 1591.5 | 1591.5 | 1591.5 | — | 0 | 0 | 0 | 0 | 2266886 |
| capacity-smoke | order_retry | 1 | 68.9 | 68.9 | 68.9 | — | 0 | 0 | 0 | 0 | 3423 |
| capacity-smoke | home | 1 | 91.4 | 91.4 | 91.4 | — | 0 | 0 | 0 | 0 | 11428 |
| capacity-smoke | storefront | 1 | 64.8 | 64.8 | 64.8 | — | 0 | 0 | 0 | 0 | 944 |

الرحلات أدناه تشمل وقت التفكير2–5ث بين الخطوات، وتُفصل عن SLA زمن HTTP. محاولات حدود النافذة محفوظة خامًا وتظهر بعد كل مرحلة.

| المرحلة | الرحلة | n | إخفاقات داخل النافذة | p50 ms | p95 ms | p99 ms |
|---|---|---:|---:|---:|---:|---:|
| policy-smoke | search | 3 | 0 | 2807.2 | 3925.4 | 3925.4 |
| policy-smoke | checkout | 3 | 1 | 9056.2 | 10257.6 | 10257.6 |
| policy-smoke | browse | 2 | 0 | 14049.4 | 14574.9 | 14574.9 |

محاولات حدود نافذة policy-smoke: 0. تبقى السجلات الأصلية والتلخيص القديم محفوظين؛ هذا تلخيص مشتق يفصل رحلة قُطعت عند نهاية زمن القياس.

| capacity-smoke | search | 2 | 0 | 2624.2 | 3405.6 | 3405.6 |
| capacity-smoke | checkout | 1 | 0 | 8384.8 | 8384.8 | 8384.8 |
| capacity-smoke | browse | 1 | 0 | 15286.0 | 15286.0 | 15286.0 |

محاولات حدود نافذة capacity-smoke: 0. تبقى السجلات الأصلية والتلخيص القديم محفوظين؛ هذا تلخيص مشتق يفصل رحلة قُطعت عند نهاية زمن القياس.


التوقف بسبب ذاكرة المضيف يعني أن الكمبيوتر المشترك تجاوز الحد؛ لا يثبت تشبع Django. لا نعرض throughput مستدامًا لجولة ناقصة. أزمنة HTTP الجزئية تضم شبكة Docker وNginx، وليست زمن SQL وحده.


محاولة سابقة محفوظة: [report.json](<../tools/performance/artifacts/20261017-campaign/report.json>).

- policy: مستخدمون 1، طلبات 19، اكتمال False، السبب host_memory_above_90_percent_for_60s. لا تُستبعد هذه المحاولة من المقارنة.
- capacity: مستخدمون 1، طلبات 17، اكتمال False، السبب host_memory_above_90_percent_for_60s. لا تُستبعد هذه المحاولة من المقارنة.

إعدادات وإصدارات Docker المسجلة: [runtime-resumed.json](<../tools/performance/artifacts/runtime-resumed.json>). يوضح الملف حدود الحاويات الفعلية؛ الصفر يعني عدم تعيين حد صريح للحاوية، وليس موارد غير محدودة للمضيف.

مهام الخلفية: [task-timings-resumed.json](<../tools/performance/artifacts/task-timings-resumed.json>). هذه عينات تحقق محلية منفصلة عن قبول الحمل؛ لا تمثل p95 للطوابير تحت100 مستخدم.

| المهمة | النتيجة | انتظار الطابور ms | التنفيذ ms |
|---|---|---:|---:|
| accounts.tasks.send_email_task | SUCCESS | 18.448829650878906 | 113.52306099996667 |
| dashboard.tasks.monitor_media_jobs | SUCCESS | 7.348775863647461 | 70.44585800002778 |

مستقبل البريد: [mail-sink-verification.json](<../tools/performance/artifacts/mail-sink-verification.json>)؛ رسائل التحقق الصناعية المطابقة: 1. لا يُفسر الزمن كتسليم مزود بريد خارجي.
### تشخيص SQL مستقل

الدليل: [query-diagnostics.json](<../tools/performance/artifacts/query-diagnostics.json>). لا تُقارن هذه الأزمنة مباشرة بقياس HTTP.

| السيناريو | كتالوج | طلبات الحساب | الاستعلامات | SQL ms | الزمن الكلي ms | حجم الرد bytes |
|---|---:|---:|---:|---:|---:|---:|
| page_30 | 100 | — | 12 | 214.6 | 1074.6 | 13808 |
| metadata | 100 | — | 7 | 12.8 | 30.8 | 940 |
| order_history_1000 | 100 | 10 | 6 | 147.3 | 181.8 | 22271 |
| page_30 | 1000 | — | 12 | 46.9 | 97.1 | 13947 |
| metadata | 1000 | — | 7 | 9.4 | 22.2 | 942 |
| order_history_1000 | 1000 | 1009 | 17 | 97.5 | 2208.5 | 2256620 |
| page_30 | 10000 | — | 12 | 101.2 | 124.8 | 14068 |
| metadata | 10000 | — | 7 | 26.7 | 40.6 | 944 |
| order_history_1000 | 10000 | 1009 | 17 | 175.2 | 2182.0 | 2256620 |

سجل الطلبات الكبير مرشح أولويّة: راجع حجم الاستجابة وتجهيز/ترميز القوائم، ثم اقترح pagination متوافقًا مع العميل في عمل منفصل. هذه توصية مبنية على نسبة زمن SQL إلى الزمن الكلي وحجم الرد، وليست إصلاحًا منفذًا أو حكمًا على الإنتاج.

## بدء التشغيل والذاكرة

بدء التشغيل: [startup.json](<../../yalla_market/build/performance/startup-v2/startup.json>). المقاييس تبدأ من Dart main أو callback الاستئناف حسب اسم العمود، وAndroid TotalTime محفوظ منفصلًا. Firebase والإشعارات مستبعدة من الحزمة المعزولة.

محاولة uninstall أعادت DELETE_FAILED_INTERNAL_ERROR ثم نجح install وتغير firstInstallTime إلى وقت الجلسة. قياس أول تشغيل محفوظ، لكن تفريغ كل البيانات السابقة لم يتحقق بصورة مستقلة، فلا يُعتمد كأول تشغيل نظيف مؤكد.

| الحالة | المقياس | العينات | الوسيط ms | p95 ms |
|---|---|---:|---:|---:|
| first_install | dart_main_to_raster_ms | 1 | 890.09 | 890.09 |
| first_install | dart_main_to_content_ms | 1 | 6426.56 | 6426.56 |
| first_install | Android TotalTime | 1 | 1505.00 | 1505.00 |
| process_stopped_disk_cache_preserved | dart_main_to_raster_ms | 30 | 126.17 | 163.45 |
| process_stopped_disk_cache_preserved | dart_main_to_content_ms | 30 | 2709.54 | 4411.61 |
| process_stopped_disk_cache_preserved | Android TotalTime | 30 | 480.00 | 594.00 |
| background_return | resume_to_raster_ms | 30 | 23.62 | 35.84 |
| background_return | resume_to_content_ms | 30 | 23.62 | 35.84 |
| background_return | Android TotalTime | 30 | 122.00 | 143.00 |

التحقق من عينات الساعات: first_install/dart_main_to_raster_ms: 1/1; first_install/dart_main_to_content_ms: 1/1; process_stopped_disk_cache_preserved/dart_main_to_raster_ms: 30/30; process_stopped_disk_cache_preserved/dart_main_to_content_ms: 30/30; background_return/resume_to_raster_ms: 30/30; background_return/resume_to_content_ms: 30/30. القيم السالبة والعلامات المفقودة لا تُحوّل إلى أصفار أو نجاح.

موارد Android: [resources.jsonl](<../../yalla_market/build/performance/device-resumed-current-cpu/resources.jsonl>)؛ 312 عينة خلال 1556ث. PSS أول/آخر/أقصى MiB: 297.47265625 / 318.5009765625 / 330.6923828125.
CPU من نوافذ حديثة: 312 عينة، المتوسط 16.66570512820513% من نواة واحدة، وأقصى عينة 66.0%. حرارة البطارية القصوى 33.3°C. CPU القديم من cpuinfo مستبعد؛ العينات لا تثبت القمة المستمرة أو عمر البطارية.

موارد Android: [resources.jsonl](<../../yalla_market/build/performance/device-resumed-session/resources.jsonl>)؛ 49 عينة خلال 240ث. PSS أول/آخر/أقصى MiB: 300.7763671875 / 296.1142578125 / 309.1806640625.
CPU من نوافذ حديثة: 0 عينة، المتوسط None% من نواة واحدة، وأقصى عينة None%. حرارة البطارية القصوى 31.5°C. CPU القديم من cpuinfo مستبعد؛ العينات لا تثبت القمة المستمرة أو عمر البطارية.

لقطات الذاكرة منفصلة عن قياس الإطارات؛ GC المفروض واللقطات يؤثران على التشغيل:

- [after20.heapsnapshot](<../../yalla_market/build/performance/memory-resumed/after20.heapsnapshot>): 12,735,266 bytes من بيانات heap graph، وليست إجمالي RAM.
- [after_soak.heapsnapshot](<../../yalla_market/build/performance/memory-resumed/after_soak.heapsnapshot>): 12,775,683 bytes من بيانات heap graph، وليست إجمالي RAM.
- [baseline.heapsnapshot](<../../yalla_market/build/performance/memory-resumed/baseline.heapsnapshot>): 12,763,019 bytes من بيانات heap graph، وليست إجمالي RAM.
- [after20.growth.json](<../../yalla_market/build/performance/memory-resumed/after20.growth.json>): 0 أصناف مرشحة للنمو ضمن العينة؛ نمو الكائنات لا يثبت التسريب، وعدم نمو العينة لا يثبت غيابه.
- [after_soak.growth.json](<../../yalla_market/build/performance/memory-resumed/after_soak.growth.json>): 1 أصناف مرشحة للنمو ضمن العينة؛ نمو الكائنات لا يثبت التسريب، وعدم نمو العينة لا يثبت غيابه.
  الصنف `_SuspendState`: زيادة 1 كائن؛ retaining path لعينة من الصنف، ولا يثبت أن العينة هي الكائن الجديد نفسه.

| نقطة GC | Dart heap مستخدم MiB | سعة heap MiB | external MiB |
|---|---:|---:|---:|
| baseline | 25.503 | 27.211 | 0.015 |
| after20 | 25.553 | 27.711 | 0.015 |
| after_soak | 25.632 | 27.711 | 0.015 |

الجلسة: 30 دقيقة؛ الدورات: 543؛ اكتمال: True.
RSS الموصوف من داخل العملية: أول عينة 276.8MiB، الأخيرة 298.6MiB، القمة 312.0MiB؛ عدد العينات 543. هذه ليست قراءة PSS ولا دليل تسريب منفردًا.

## التغطية والحدود

| السيناريو | الحالة | السبب/الدليل |
|---|---|---|
| all | measured_with_motion_limit | ..\yalla_market\build\performance\run-20261017-ar-all.raw.json |
| all | partial | ..\yalla_market\build\performance\run-20261017-ar-motion-v2.raw.json |
| search_navigation | measured | ..\yalla_market\build\performance\run-20261017-ar-search-v3.raw.json |
| store | partial | ..\yalla_market\build\performance\run-20261017-ar-store.raw.json |
| category | measured | ..\yalla_market\build\performance\run-20261017-category-calibrated.raw.json |
| browse_search | measured_with_motion_limit | ..\yalla_market\build\performance\run-20261017-en.raw.json |
| physical_offers_and_long_list_residency | partial | ..\yalla_market\build\performance\run-20261017-offers-residency.raw.json |
| store_ui_checkout_cubit_and_purchase_ui | partial | ..\yalla_market\build\performance\run-20261017-staging-purchase-v2.raw.json |
| server_capacity_10_25_50_100_soak_spike | blocked | Safety stop; no sustainable capacity inferred |
| release_startup | measured_with_clock_and_service_limits | ..\yalla_market\build\performance\startup-v2\startup.json |
| memory_20_cycles_and_30min | measured | ..\yalla_market\build\performance\memory-resumed |
| controlled_network_normal_slow_loss_offline | unmeasured | No bidirectional shaping gateway; USB forwarding is not the specified WiFi network |
| mobile_at_stable_server_load | blocked | No stable server load established after host memory safety stop |
| production_resource_parity | unverified | Local Docker Desktop resources only |
| external_FCM_delivery | unmeasured | No production tokens/providers used; local SMTP sink and queue paths only |
| Android_4GB_and_iOS | out_of_scope_current_device | Only connected Android device measured |
| image_completion_and_empty_vs_full_disk_cache | unmeasured | Bundled-image UI rounds and seeded network-image browsing are separate; no image-completion observer or controlled cache eviction was executed. First pass does not imply empty disk cache. |
| login_and_refresh_independent_30_samples | unmeasured | Login is functional setup and refresh is separately named in Locust setup metrics. A separate 30-sample authentication campaign was not completed after the host memory safety stop; authentication rate limits remain enabled. |
| scroll_position_and_search_business_correctness | partial | Pagination uniqueness and nonempty category results are asserted; existing store Cubit regressions pass. The recorded mobile baseline does not assert restored scroll offset or all search-result contents, so it does not certify those flows. |
| installation_data_cache_size_and_battery | partial | APK sizes and device temperature/charging evidence are recorded. Profile sandbox disk use can be read with run-as; release private-data size may not be available. USB charging and one device prevent a battery-life conclusion. |
| previous_interrupted_memory_session | partial_preserved | The first session returned baseline and after20 heap snapshots but no completed 30-minute artifact. Its ignored logs and snapshots remain under yalla_market/build/performance/memory; the resumed session has a separate directory. |
| monitoring_cadence_and_database_disk_io | partial | Collector targets 5 seconds and records actual timestamps. Docker block I/O and PostgreSQL cache/temp counters are collected; dedicated PostgreSQL device IOPS/latency and worker restart reasons need deeper host monitoring. No missing series is inferred as zero. |
| english_corrected_profile_attempts | partial_preserved | Three corrected attempts lost Flutter VM service connection before a raw result returned. Completion markers alone do not substitute for frame arrays. Legacy English browsing retained with motion limitations and invalid fake-client search. |
| local_image_asset_load_capacity | unmeasured | Locust journeys request API endpoints only. Physical network-image browsing is a single-device functional workload, not concurrent image asset capacity. |
| clean_first_install_startup_v2 | unconfirmed | Uninstall returned DELETE_FAILED_INTERNAL_ERROR, then install succeeded and firstInstallTime changed. The first post-install sample is preserved but independent clearance of previous private data was not verified. Cold-process and background samples are separate. |
| memory_driver_shell_status | measured_with_execution_warning | Completed 30-minute raw artifact and All tests passed log are preserved; outer PowerShell returned1 with native stderr warnings. Raw completion and snapshots support measurement, while shell status remains documented. |
| offers_three_horizontal_rounds | measured_synthetic_images | Three actual horizontal30s rounds returned FrameTiming and all passed. The same test later failed at Home due missing RegionHintCubit in its fixture. Valid offers results retained. |
| list_resident_widget_counts | unmeasured_fixture_failure | Home fixture missed NavigationMenuView provider. Harness corrected, but corrected version was not built or rerun before delivery. Earlier long-list frame rounds remain separate evidence; no resident count is fabricated. |
| profile_30_purchase_ui_journeys | unmeasured_fixture_failure | Initial live-frame appContext was uninitialized before the route built. Harness now waits and corrected APK is built, but has not run. One actual Release purchase review passed; this does not substitute for30 latency samples. |

## الأولويات

1. توفير ذاكرة كافية وفصل مولد الحمل عن الاستضافة المحلية، ثم إعادة الحملة كاملة لتحديد مستوى مختبر مستقر.
2. تشخيص استجابة سجل الطلبات الكبير وحجمها؛ اختبر أي اقتراح pagination لاحقًا بنفس البيانات.
3. راجع نتائج الفئات بالمسار الفعلي المسجل؛ الإخفاق المتكرر بعد معايرة الإدخال يحتاج تحليل build/paint/raster في trace قبل اختيار إصلاح.
4. استكمال الشبكات المضبوطة وجهاز4GB قبل تعميم تجربة الصور والبطارية والذاكرة.

لم تُنفذ تحسينات أداء أو تغييرات في عقود API أو نشر للإنتاج. لم تُنشأ migrations جديدة؛ طُبقت migrations الموجودة فقط على قاعدة Docker المعزولة عند تجهيزها.

### مشكلة مرصودة: سلاسة تغيير الفئات

لم تجتز 15 جولات معيار السلاسة مع مسار إدخال الجهاز. أعلى نسبة Raster متأخر: 24.69%. الأثر: تقطيع خلال التصفح وتبديل النتائج. الثقة عالية في رصد الإخفاق ضمن نافذة الاختبار؛ السبب الجذري غير محسوم. الفرضية التي تُفحص لاحقًا هي تكلفة إعادة بناء/رسم البطاقات والـslivers عند تبديل النتائج. لا تكفي البيانات الحالية لنسبة المشكلة إلى عنصر واحد أو صورة بعينها.
اقتراح المتابعة: طابق إطارات trace البطيئة مع build/layout/paint وRaster، ثم اختبر تحسينًا واحدًا في تجربة مستقلة بنفس الإدخال والبيانات. لم ينفذ هذا التقرير إصلاحًا.

## مراجعة رحلة الشراء على Release

الحالة: اجتازت. الدليل: [release-review.json](<../../yalla_market/build/performance/release-review-v2/release-review.json>). تستخدم callbacks لعناصر الواجهة المعروضة؛ لا تمثل قياس زمن اللمس، والإشعارات الخارجية معزولة.

## تشخيص trace للفئات

جولات trace منفصلة عن حكم السلاسة لتأثير جمعها. زمن SurfaceFrame::Submit وGPURasterizer::Draw هو المرشح الأقوى لتأخر Raster المتكرر، مع قفزات BUILD أيضًا. لا تحدد هذه الأحداث وحدها widget مسؤولًا أو تكلفة كل saveLayer؛ الأزمنة المتداخلة لا تُجمع.
- [run-20261017-category-trace.summary-store_1000_category_1_trace.trace.spans.json](<../../yalla_market/build/performance/run-20261017-category-trace.summary-store_1000_category_1_trace.trace.spans.json>)
- [run-20261017-category-trace.summary-store_1000_category_2_trace.trace.spans.json](<../../yalla_market/build/performance/run-20261017-category-trace.summary-store_1000_category_2_trace.trace.spans.json>)
- [run-20261017-category-trace.summary-store_1000_category_3_trace.trace.spans.json](<../../yalla_market/build/performance/run-20261017-category-trace.summary-store_1000_category_3_trace.trace.spans.json>)
