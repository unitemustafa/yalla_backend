"""Build a reviewable Arabic report from evidence, with explicit coverage gaps."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.performance.metrics import distribution, journeys_summary
from tools.performance.summarize import summarize_mobile
from tools.performance.resources import summarize_resources


def load(path):
    return (
        json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--previous-server", type=Path, action="append", default=[])
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--mail", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--suite-id", default="local-baseline")
    parser.add_argument("--mobile", type=Path, action="append", default=[])
    parser.add_argument("--device", type=Path)
    parser.add_argument("--startup", type=Path)
    parser.add_argument("--release-review", type=Path)
    parser.add_argument("--trace-summary", type=Path, action="append", default=[])
    parser.add_argument("--memory", type=Path)
    parser.add_argument("--memory-session", type=Path)
    parser.add_argument("--resources", type=Path, action="append", default=[])
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument(
        "--coverage", type=Path, help="Additional documented scenario gaps"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def link(path):
        relative = os.path.relpath(path.resolve(), output.parent).replace("\\", "/")
        return f"[{path.name}](<{relative}>)"

    lines = [
        f"# خط أساس أداء يلا ماركت — {args.date}",
        "",
        f"معرف التجربة الجامع: `{args.suite_id}`؛ تحتفظ كل مرحلة بمعرفها وملفاتها الأصلية.",
        "",
        "النتائج تخص الجهاز وبيئة Docker المحليين. لا يحدد هذا التقرير سعة الإنتاج، ولا يتضمن تنفيذ تحسينات.",
        "",
        "## النتائج العملية وخطوات العلاج",
        "",
        "- **تقطيع تغيير الفئات:** تأخر Raster متكرر حتى24.69% من الإطارات في الجولات المصححة، مقابل حد أقل من5%. trace يضع تكلفة GPU Draw/Submit في مقدمة التشخيص. العلاج المقترح: تحديد البطاقة/طبقة الرسم المسؤولة داخل الإطارات البطيئة، ثم تقليل إعادة رسمها وإعادة الجولات نفسها؛ لا يوجد دليل كافٍ الآن لاختيار تعديل widget بعينه.",
        "- **سجل الطلبات الكبير:** نحو2.26MB و2.2ث في تشخيص in-process، مع زمن SQL أقل بكثير. العلاج المقترح: تقسيم سجل الطلبات إلى صفحات وتحميل التفاصيل عند الطلب، بتغيير متوافق بين السيرفر والعميل في مهمة إصلاح مستقلة. هذه فرضية قوية تحتاج مقارنة قبل/بعد، وليست إصلاحًا منفذًا.",
        "- **سعة السيرفر غير محسومة:** نجح smoke بمستخدم واحد، لكن RAM المضيف8GB تجاوزت حد الأمان. الخطوة المطلوبة: فصل مولد الحمل وتوفير موارد اختبار كافية، ثم إعادة10/25/50/100؛ لا يجوز نسبة هذا التوقف إلى تشبع Django.",
        "- **الشراء وبدء التشغيل والذاكرة:** مراجعة شراء Release اجتازت؛30 تشغيلًا باردًا و30 عودة مسجلة؛ جلسة الذاكرة30 دقيقة اكتملت. التفاصيل والحدود أدناه، ومنها أن مراجعة Release ليست30 رحلة لمس وأن صور الكاش والشبكات المضبوطة لم تستكمل.",
        "",
    ]
    coverage, mobile_results = [], []
    if args.sources and args.sources.exists():
        lines += [f"نسخ الكود والبناء وبصمات ملفات القياس: {link(args.sources)}.", ""]
    device = load(args.device)
    if device:
        lines += [
            "## الجهاز والمنهج",
            "",
            f"الجهاز: {device['model']}، Android {device['android']}، ABI: {device['abi']}.",
            f"الذاكرة المسجلة: {device['memory'][0]}؛ الوصول: {device['accessibility_enabled']}؛ لم تغير الأداة إعدادات الجهاز.",
            f"دليل الجهاز: {link(args.device)}. قياس الطاقة محدود بسبب شحن USB.",
            "",
        ]
    lines += [
        "## الواجهة والتفاعل",
        "",
        "النسب التالية هي **أسوأ جولة** لكل سيناريو، وليست متوسطًا يخفي الجولات الفاشلة. ميزانية الإطار حسب التردد المسجل؛ الحد أقل من5% لكل من UI وRaster، ولا إطار أكبر من100ms.",
        "",
    ]
    for path in args.mobile:
        raw = load(path)
        if raw is None:
            coverage.append(
                {
                    "scenario": path.name,
                    "status": "unmeasured",
                    "reason": "No returned test artifact",
                }
            )
            continue
        value = summarize_mobile(raw)
        mobile_results.append({"artifact": str(path), "summary": value})
        lines += [
            f"### {path.stem}",
            "",
            f"النطاق: {raw.get('scope')}؛ اللغة: {raw.get('language')}؛ المصدر: {raw.get('data_source')}؛ اكتمال السيناريو: {raw.get('completed', False)}.",
            f"الإدخال: {raw.get('input_route', 'legacy_test_pointer')}؛ semantics المفروضة بالاختبار: {raw.get('test_forced_semantics', 'legacy_true')}.",
            f"توثيق الحركة: `{value['scroll_motion_quality']}`؛ trace تشخيصي: {raw.get('trace_diagnostic', False)}. الجولات القديمة لا تثبت استمرار حركة القائمة طوال النافذة.",
            f"صلاحية إدخال البحث: `{value['search_input_quality']}`. نتائج البحث القديمة الناتجة من fake text client في Profile ليست زمن استعلام فعلي، وتظل محفوظة كأثر لأداة القياس.",
            f"البيانات الخام: {link(path)}.",
            "",
            "| السيناريو | الجولات | إطارات UI/Raster لكل جولة | أقصى تأخر UI % | أقصى تأخر Raster % | أقصى إطار ms | كل الجولات اجتازت؟ |",
            "|---|---:|---|---:|---:|---:|---|",
        ]
        grouped = {}
        for name, scenario in value["scenarios"].items():
            grouped.setdefault(re.sub(r"_\d+$", "", name), []).append(scenario)
        for name, repeats in grouped.items():
            ui = max(r["ui"]["late_percent"] or 0 for r in repeats)
            raster = max(r["raster"]["late_percent"] or 0 for r in repeats)
            maximum = max(
                max(r["ui"]["max_ms"] or 0, r["raster"]["max_ms"] or 0) for r in repeats
            )
            passes = all(r["passes"] for r in repeats)
            counts = ", ".join(f"{r['ui']['n']}/{r['raster']['n']}" for r in repeats)
            lines.append(
                f"| {name} | {len(repeats)} | {counts} | {ui:.2f} | {raster:.2f} | {maximum:.2f} | {'نعم' if passes else 'لا'} |"
            )
        if value["actions"]:
            lines += [
                "",
                "| التفاعل | العينات | الوسيط ms | p95 ms | p99 ms |",
                "|---|---:|---:|---:|---:|",
            ]
            for name, metric in value["actions"].items():
                label = name
                if (
                    "search" in name
                    and value["search_input_quality"]
                    == "invalid_legacy_profile_text_input"
                ):
                    label += " (غير صالح لزمن البحث)"
                lines.append(
                    f"| {label} | {metric['n']} | {metric['p50_ms']:.2f} | {metric['p95_ms']:.2f} | {metric['p99_ms']:.2f} |"
                )
        residents = {
            name: observation
            for name, observation in value["observations"].items()
            if isinstance(observation, dict)
            and observation.get("item_widget_count_kind")
            == "resident_live_element_count"
        }
        if residents:
            lines += [
                "",
                "| القائمة | عناصر مقيمة قبل/بعد | RSS قبل/بعد MiB | كاش الصور بعد bytes |",
                "|---|---|---|---:|",
            ]
            for name, observation in residents.items():
                before, after = (
                    observation["memory_before"],
                    observation["memory_after"],
                )
                lines.append(
                    f"| {name} | {observation.get('resident_item_widgets_before', 'غير مقاس')}/{observation.get('resident_item_widgets_after', 'غير مقاس')} | {before['rss_bytes'] / 1048576:.1f}/{after['rss_bytes'] / 1048576:.1f} | {after['image_cache_bytes']} |"
                )
            lines += [
                "",
                "العدد هو عناصر حية في الشجرة، وليس مجموع استدعاءات build؛ عينات RSS والكاش وصفية ولا تثبت تسريبًا.",
            ]
        lines += [
            "",
            "هذه أزمنة التعريف المسجل لنهاية التفاعل؛ قياس Cubit لا يساوي زمن الزر إلى الرسم. الصور المحلية المتكررة لا تثبت أداء صور الشبكة. الجولات القديمة ذات مسار مؤشر الاختبار وsemantics الإضافية دليل حساسية للأداة، ولا تكفي وحدها لنسبة التقطيع لاستخدام اليد.",
            "نافذة إطارات الفئات تضم إعادة التمرير للأعلى وإظهار الفئة والنقر وانتظار الاستقرار؛ زمن التفاعل المفرد يبدأ قبل النقر. أول مرور محفوظ منفصلًا لكنه لا يثبت أن كاش الصور أو القرص كان فارغًا.",
            "",
        ]
        coverage.append(
            {
                "scenario": raw.get("scope"),
                "status": (
                    "measured_with_motion_limit"
                    if value["scroll_motion_quality"] == "legacy_motion_unverified"
                    else "measured"
                )
                if raw.get("completed")
                else "partial",
                "evidence": str(path),
            }
        )
    server = load(args.server / "report.json")
    lines += ["## السيرفر", ""]
    if server:
        lines += [
            f"الدليل: {link(args.server / 'report.json')}، والموارد: {link(args.server / 'inventory.json')}.",
            "",
            "| المسار/المرحلة | المستخدمون | طلبات نافذة القياس | أخطاء غير متوقعة | 429 | اكتمال | سبب التوقف |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
        for result in server["results"]:
            lines.append(
                f"| {result.get('stage', result['route'])} | {result['users']} | {result['requests']} | {result['unexpected_failures']} | {result['rate_limited']} | {result['complete']} | {result['stop_reason'] or '—'} |"
            )
        lines += [
            "",
            "أزمنة endpoints مع أحجام العينات؛ الجولة الناقصة لا يُستنتج منها RPS مستدام:",
            "",
            "| المرحلة | endpoint | n | p50 ms | p95 ms | p99 ms | RPS صالح | 4xx بدون429 | 429 | 5xx | شبكة | متوسط bytes |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for result in server["results"]:
            for name, metric in result.get("groups", {}).items():
                codes = {
                    int(code): count
                    for code, count in metric.get("statuses", {}).items()
                    if code.isdigit()
                }
                rate = (
                    f"{metric['rps']:.3f}" if result.get("throughput_usable") else "—"
                )
                lines.append(
                    f"| {result.get('stage', result['route'])} | {name} | {metric['n']} | {metric['p50_ms']:.1f} | {metric['p95_ms']:.1f} | {metric['p99_ms']:.1f} | {rate} | {sum(v for c, v in codes.items() if 400 <= c < 500 and c != 429)} | {codes.get(429, 0)} | {sum(v for c, v in codes.items() if 500 <= c < 600)} | {codes.get(0, 0)} | {metric['bytes'] / metric['n']:.0f} |"
                )
        stopped = any(result["stop_reason"] for result in server["results"])
        lines += [
            "",
            "الرحلات أدناه تشمل وقت التفكير2–5ث بين الخطوات، وتُفصل عن SLA زمن HTTP. محاولات حدود النافذة محفوظة خامًا وتظهر بعد كل مرحلة.",
            "",
            "| المرحلة | الرحلة | n | إخفاقات داخل النافذة | p50 ms | p95 ms | p99 ms |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for stage in server["results"]:
            folder = args.server / stage.get("stage", f"{stage['route']}-smoke")
            path = folder / "journeys.jsonl"
            timing = load(folder / "timing.json")
            if not path.exists() or not timing:
                continue
            start = timing["start_epoch"] + timing["ramp_s"] + timing["warmup_s"]
            value = journeys_summary(
                [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                ],
                start,
                start + timing["planned_measurement_s"],
            )
            stage["journey_window_summary"] = value
            for name, metric in value["groups"].items():
                lines.append(
                    f"| {stage.get('stage', stage['route'])} | {name} | {metric['n']} | {metric['failures']} | {metric['p50_ms']:.1f} | {metric['p95_ms']:.1f} | {metric['p99_ms']:.1f} |"
                )
            lines.append(
                f"\nمحاولات حدود نافذة {stage.get('stage', stage['route'])}: {value['boundary_rows']}. تبقى السجلات الأصلية والتلخيص القديم محفوظين؛ هذا تلخيص مشتق يفصل رحلة قُطعت عند نهاية زمن القياس.\n"
            )
        lines += [
            "",
            "التوقف بسبب ذاكرة المضيف يعني أن الكمبيوتر المشترك تجاوز الحد؛ لا يثبت تشبع Django. لا نعرض throughput مستدامًا لجولة ناقصة. أزمنة HTTP الجزئية تضم شبكة Docker وNginx، وليست زمن SQL وحده.",
            "",
        ]
        coverage.append(
            {
                "scenario": "server_capacity_10_25_50_100_soak_spike",
                "status": "blocked" if stopped else "see_stage_results",
                "reason": "Safety stop; no sustainable capacity inferred"
                if stopped
                else "Only fully measured stages can establish a tested level",
            }
        )
    queries = load(args.queries)
    previous_servers = []
    for folder in args.previous_server:
        previous = load(folder / "report.json")
        if previous:
            previous_servers.append(previous)
            lines += ["", f"محاولة سابقة محفوظة: {link(folder / 'report.json')}.", ""]
            for stage in previous["results"]:
                lines.append(
                    f"- {stage.get('stage', stage['route'])}: مستخدمون {stage['users']}، طلبات {stage['requests']}، اكتمال {stage['complete']}، السبب {stage.get('stop_reason') or 'لا توقف أمان'}. لا تُستبعد هذه المحاولة من المقارنة."
                )
    runtime = load(args.runtime)
    if runtime:
        lines += [
            "",
            f"إعدادات وإصدارات Docker المسجلة: {link(args.runtime)}. يوضح الملف حدود الحاويات الفعلية؛ الصفر يعني عدم تعيين حد صريح للحاوية، وليس موارد غير محدودة للمضيف.",
        ]
    tasks = load(args.tasks)
    mail = load(args.mail)
    if tasks:
        lines += [
            "",
            f"مهام الخلفية: {link(args.tasks)}. هذه عينات تحقق محلية منفصلة عن قبول الحمل؛ لا تمثل p95 للطوابير تحت100 مستخدم.",
            "",
            "| المهمة | النتيجة | انتظار الطابور ms | التنفيذ ms |",
            "|---|---|---:|---:|",
        ]
        for event in tasks.get("events", []):
            lines.append(
                f"| {event['task_name']} | {event['status']} | {event.get('queue_wait_ms')} | {event.get('duration_ms')} |"
            )
    if mail:
        lines += [
            "",
            f"مستقبل البريد: {link(args.mail)}؛ رسائل التحقق الصناعية المطابقة: {mail['matching_synthetic_subject']}. لا يُفسر الزمن كتسليم مزود بريد خارجي.",
        ]
    if queries:
        lines += [
            "### تشخيص SQL مستقل",
            "",
            f"الدليل: {link(args.queries)}. لا تُقارن هذه الأزمنة مباشرة بقياس HTTP.",
            "",
            "| السيناريو | كتالوج | طلبات الحساب | الاستعلامات | SQL ms | الزمن الكلي ms | حجم الرد bytes |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in queries["scenarios"]:
            lines.append(
                f"| {row['scenario']} | {row['catalog_count']} | {row.get('history_count') or '—'} | {row['query_count']} | {row['sql_ms']:.1f} | {row['elapsed_ms']:.1f} | {row['response_bytes']} |"
            )
        lines += [
            "",
            "سجل الطلبات الكبير مرشح أولويّة: راجع حجم الاستجابة وتجهيز/ترميز القوائم، ثم اقترح pagination متوافقًا مع العميل في عمل منفصل. هذه توصية مبنية على نسبة زمن SQL إلى الزمن الكلي وحجم الرد، وليست إصلاحًا منفذًا أو حكمًا على الإنتاج.",
            "",
        ]
    startup = load(args.startup)
    startup_validation = []
    lines += ["## بدء التشغيل والذاكرة", ""]
    if startup:
        lines += [
            f"بدء التشغيل: {link(args.startup)}. المقاييس تبدأ من Dart main أو callback الاستئناف حسب اسم العمود، وAndroid TotalTime محفوظ منفصلًا. Firebase والإشعارات مستبعدة من الحزمة المعزولة.",
            "",
            "| الحالة | المقياس | العينات | الوسيط ms | p95 ms |",
            "|---|---|---:|---:|---:|",
        ]
        if startup.get("first_install_context"):
            lines[-2:-2] = [startup["first_install_context"], ""]
        protocol_valid = any(
            e.get("observer_protocol") == "interactive_entry_raster_v2"
            for sample in startup["samples"]
            for e in sample.get("events", [])
        )
        for mode in (
            "first_install",
            "process_stopped_disk_cache_preserved",
            "background_return",
        ):
            keys = (
                ("resume_to_raster_ms", "resume_to_content_ms")
                if mode == "background_return"
                else ("dart_main_to_raster_ms", "dart_main_to_content_ms")
            )
            for key in keys:
                values = [
                    event[key]
                    for sample in startup["samples"]
                    if sample["state"] == mode
                    if protocol_valid
                    for event in sample.get("events", [])
                    if key in event and event[key] >= 0
                ]
                expected = 1 if mode == "first_install" else 30
                startup_validation.append(
                    {
                        "state": mode,
                        "metric": key,
                        "expected": expected,
                        "valid_n": len(values),
                    }
                )
                if not values:
                    continue
                metric = distribution(values)
                lines.append(
                    f"| {mode} | {key} | {metric['n']} | {metric['p50_ms']:.2f} | {metric['p95_ms']:.2f} |"
                )
            native = [
                float(match.group(1))
                for sample in startup["samples"]
                if sample["state"] == mode
                if (
                    match := re.search(
                        r"TotalTime:\s*(\d+)", sample.get("android_activity_start", "")
                    )
                )
            ]
            if native:
                metric = distribution(native)
                lines.append(
                    f"| {mode} | Android TotalTime | {metric['n']} | {metric['p50_ms']:.2f} | {metric['p95_ms']:.2f} |"
                )
        coverage.append(
            {
                "scenario": "release_startup",
                "status": "measured_with_clock_and_service_limits"
                if startup_validation
                and all(row["expected"] == row["valid_n"] for row in startup_validation)
                else "partial_missing_or_invalid_clock_markers",
                "evidence": str(args.startup),
            }
        )
        lines += [
            "",
            "التحقق من عينات الساعات: "
            + "; ".join(
                f"{row['state']}/{row['metric']}: {row['valid_n']}/{row['expected']}"
                for row in startup_validation
            )
            + ". القيم السالبة والعلامات المفقودة لا تُحوّل إلى أصفار أو نجاح.",
        ]
    else:
        coverage.append(
            {
                "scenario": "release_startup",
                "status": "unmeasured",
                "reason": "No completed release startup artifact",
            }
        )
    session = load(args.memory_session)
    resource_results = []
    for path in args.resources:
        if not path.exists():
            continue
        value = summarize_resources(
            [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        )
        resource_results.append({"artifact": str(path), "summary": value})
        lines += [
            "",
            f"موارد Android: {link(path)}؛ {value['samples']} عينة خلال {value['duration_s']:.0f}ث. PSS أول/آخر/أقصى MiB: {value['pss_first_mib']} / {value['pss_last_mib']} / {value['pss_max_mib']}.",
            f"CPU من نوافذ حديثة: {value['current_cpu_samples']} عينة، المتوسط {value['cpu_mean_one_core_percent']}% من نواة واحدة، وأقصى عينة {value['cpu_max_sample_one_core_percent']}%. حرارة البطارية القصوى {value['battery_max_c']}°C. CPU القديم من cpuinfo مستبعد؛ العينات لا تثبت القمة المستمرة أو عمر البطارية.",
        ]
    if args.memory and args.memory.exists():
        snapshots = sorted(args.memory.glob("*.heapsnapshot"))
        lines += [
            "",
            "لقطات الذاكرة منفصلة عن قياس الإطارات؛ GC المفروض واللقطات يؤثران على التشغيل:",
            "",
        ]
        for snapshot in snapshots:
            lines.append(
                f"- {link(snapshot)}: {snapshot.stat().st_size:,} bytes من بيانات heap graph، وليست إجمالي RAM."
            )
        for growth in sorted(args.memory.glob("*.growth.json")):
            value = load(growth)
            lines.append(
                f"- {link(growth)}: {len(value['classes'])} أصناف مرشحة للنمو ضمن العينة؛ نمو الكائنات لا يثبت التسريب، وعدم نمو العينة لا يثبت غيابه."
            )
            for candidate in value["classes"]:
                lines.append(
                    f"  الصنف `{candidate['class']}`: زيادة {candidate['instance_delta']} كائن؛ retaining path لعينة من الصنف، ولا يثبت أن العينة هي الكائن الجديد نفسه."
                )
        lines += [
            "",
            "| نقطة GC | Dart heap مستخدم MiB | سعة heap MiB | external MiB |",
            "|---|---:|---:|---:|",
        ]
        for name in ("baseline", "after20", "after_soak"):
            profile = load(args.memory / f"{name}.allocations.json")
            if profile and (usage := profile.get("memoryUsage")):
                lines.append(
                    f"| {name} | {usage['heapUsage'] / 1048576:.3f} | {usage['heapCapacity'] / 1048576:.3f} | {usage['externalUsage'] / 1048576:.3f} |"
                )
        if session:
            lines += [
                "",
                f"الجلسة: {session.get('soak_minutes')} دقيقة؛ الدورات: {session.get('cycles')}؛ اكتمال: {session.get('completed')}.",
            ]
            rss = [
                sample["rss_bytes"] / 1048576
                for sample in session.get("rss_samples", [])
            ]
            if rss:
                lines += [
                    f"RSS الموصوف من داخل العملية: أول عينة {rss[0]:.1f}MiB، الأخيرة {rss[-1]:.1f}MiB، القمة {max(rss):.1f}MiB؛ عدد العينات {len(rss)}. هذه ليست قراءة PSS ولا دليل تسريب منفردًا."
                ]
        coverage.append(
            {
                "scenario": "memory_20_cycles_and_30min",
                "status": "measured"
                if session and session.get("completed")
                else "partial",
                "evidence": str(args.memory),
            }
        )
    coverage += [
        {
            "scenario": "controlled_network_normal_slow_loss_offline",
            "status": "unmeasured",
            "reason": "No bidirectional shaping gateway; USB forwarding is not the specified WiFi network",
        },
        {
            "scenario": "mobile_at_stable_server_load",
            "status": "blocked",
            "reason": "No stable server load established after host memory safety stop",
        },
        {
            "scenario": "production_resource_parity",
            "status": "unverified",
            "reason": "Local Docker Desktop resources only",
        },
        {
            "scenario": "external_FCM_delivery",
            "status": "unmeasured",
            "reason": "No production tokens/providers used; local SMTP sink and queue paths only",
        },
        {
            "scenario": "Android_4GB_and_iOS",
            "status": "out_of_scope_current_device",
            "reason": "Only connected Android device measured",
        },
    ]
    if args.coverage:
        coverage += load(args.coverage) or []
    lines += [
        "",
        "## التغطية والحدود",
        "",
        "| السيناريو | الحالة | السبب/الدليل |",
        "|---|---|---|",
    ]
    for row in coverage:
        lines.append(
            f"| {row['scenario']} | {row['status']} | {row.get('reason', row.get('evidence', ''))} |"
        )
    lines += [
        "",
        "## الأولويات",
        "",
        "1. توفير ذاكرة كافية وفصل مولد الحمل عن الاستضافة المحلية، ثم إعادة الحملة كاملة لتحديد مستوى مختبر مستقر.",
        "2. تشخيص استجابة سجل الطلبات الكبير وحجمها؛ اختبر أي اقتراح pagination لاحقًا بنفس البيانات.",
        "3. راجع نتائج الفئات بالمسار الفعلي المسجل؛ الإخفاق المتكرر بعد معايرة الإدخال يحتاج تحليل build/paint/raster في trace قبل اختيار إصلاح.",
        "4. استكمال الشبكات المضبوطة وجهاز4GB قبل تعميم تجربة الصور والبطارية والذاكرة.",
        "",
        "لم تُنفذ تحسينات أداء أو تغييرات في عقود API أو نشر للإنتاج. لم تُنشأ migrations جديدة؛ طُبقت migrations الموجودة فقط على قاعدة Docker المعزولة عند تجهيزها.",
    ]
    native_failures = [
        (entry["artifact"], name, metric)
        for entry in mobile_results
        if entry["summary"].get("input_route") == "device"
        for name, metric in entry["summary"]["scenarios"].items()
        if "category" in name and not metric["passes"]
    ]
    if native_failures:
        lines += [
            "",
            "### مشكلة مرصودة: سلاسة تغيير الفئات",
            "",
            f"لم تجتز {len(native_failures)} جولات معيار السلاسة مع مسار إدخال الجهاز. أعلى نسبة Raster متأخر: {max(metric['raster']['late_percent'] for _, _, metric in native_failures):.2f}%. الأثر: تقطيع خلال التصفح وتبديل النتائج. الثقة عالية في رصد الإخفاق ضمن نافذة الاختبار؛ السبب الجذري غير محسوم. الفرضية التي تُفحص لاحقًا هي تكلفة إعادة بناء/رسم البطاقات والـslivers عند تبديل النتائج. لا تكفي البيانات الحالية لنسبة المشكلة إلى عنصر واحد أو صورة بعينها.",
            "اقتراح المتابعة: طابق إطارات trace البطيئة مع build/layout/paint وRaster، ثم اختبر تحسينًا واحدًا في تجربة مستقلة بنفس الإدخال والبيانات. لم ينفذ هذا التقرير إصلاحًا.",
        ]
    release_review = load(args.release_review)
    if release_review:
        lines += [
            "",
            "## مراجعة رحلة الشراء على Release",
            "",
            f"الحالة: {'اجتازت' if release_review.get('completed') else 'لم تكتمل'}. الدليل: {link(args.release_review)}. تستخدم callbacks لعناصر الواجهة المعروضة؛ لا تمثل قياس زمن اللمس، والإشعارات الخارجية معزولة.",
        ]
        coverage.append(
            {
                "scenario": "release_purchase_review",
                "status": "measured" if release_review.get("completed") else "partial",
                "evidence": str(args.release_review),
            }
        )
    trace_results = [load(p) for p in args.trace_summary]
    if trace_results:
        lines += [
            "",
            "## تشخيص trace للفئات",
            "",
            "جولات trace منفصلة عن حكم السلاسة لتأثير جمعها. زمن SurfaceFrame::Submit وGPURasterizer::Draw هو المرشح الأقوى لتأخر Raster المتكرر، مع قفزات BUILD أيضًا. لا تحدد هذه الأحداث وحدها widget مسؤولًا أو تكلفة كل saveLayer؛ الأزمنة المتداخلة لا تُجمع.",
        ]
        lines += [f"- {link(p)}" for p in args.trace_summary]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": args.suite_id,
                "date": args.date,
                "coverage": coverage,
                "server": server,
                "previous_servers": previous_servers,
                "runtime": runtime,
                "tasks": tasks,
                "mail": mail,
                "mobile": mobile_results,
                "startup": startup,
                "startup_validation": startup_validation,
                "release_review": release_review,
                "trace_diagnostics": trace_results,
                "memory_session": session,
                "android_resources": resource_results,
                "full_plan_all_scenarios_measured": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Report: " + str(output))


if __name__ == "__main__":
    main()
