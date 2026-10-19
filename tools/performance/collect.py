"""Read-only snapshots of the explicitly named local Compose stack."""

import json
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import psutil

ROOT = Path(__file__).resolve().parent
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".env.local"),
    "-f",
    str(ROOT / "compose.yaml"),
]


def command(args, timeout=15):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=True
    ).stdout


def snapshot(base):
    result = {
        "time": time.time(),
        "host_cpu_percent": psutil.cpu_percent(),
        "host_memory_percent": psutil.virtual_memory().percent,
        "host_disk_percent": psutil.disk_usage(str(ROOT)).percent,
        "host_cores": psutil.cpu_count(),
        "errors": [],
    }
    try:
        with urlopen(base + "/readyz/", timeout=3) as response:
            result["ready"] = (
                response.status == 200 and json.load(response).get("status") == "ok"
            )
    except Exception:
        result["ready"] = False
    try:
        lines = command(COMPOSE + ["stats", "--no-stream", "--format", "json"])
        result["containers"] = [
            json.loads(line) for line in lines.splitlines() if line.strip()
        ]
        ids = command(COMPOSE + ["ps", "--all", "--quiet"]).split()
        states = command(
            [
                "docker",
                "inspect",
                "--format",
                '{"name":{{json .Name}},"state":{{json .State.Status}},"oom":{{.State.OOMKilled}},"restarts":{{.RestartCount}}}',
            ]
            + ids
        )
        result["container_states"] = [
            json.loads(line) for line in states.splitlines() if line.strip()
        ]
    except (subprocess.SubprocessError, ValueError):
        result["errors"].append("container_stats_unavailable")
    try:
        query = """SELECT json_build_object(
          'connections',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()),
          'waiting',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'),
          'deadlocks',deadlocks,'blks_read',blks_read,'blks_hit',blks_hit,
          'temp_bytes',temp_bytes,'tup_inserted',tup_inserted)
          FROM pg_stat_database WHERE datname=current_database();"""
        result["database"] = json.loads(
            command(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "perf",
                    "-d",
                    "yalla_perf",
                    "-At",
                    "-c",
                    query,
                ]
            )
        )
        info = command(COMPOSE + ["exec", "-T", "redis", "redis-cli", "INFO"])
        result["redis"] = {
            key: value
            for line in info.splitlines()
            if ":" in line
            for key, value in [line.split(":", 1)]
            if key
            in {
                "used_memory",
                "maxmemory",
                "evicted_keys",
                "keyspace_hits",
                "keyspace_misses",
                "blocked_clients",
            }
        }
        result["queues"] = {
            queue: int(
                command(
                    COMPOSE
                    + ["exec", "-T", "redis", "redis-cli", "-n", "3", "LLEN", queue]
                )
            )
            for queue in ("notifications", "mail", "default", "media")
        }
    except (subprocess.SubprocessError, ValueError):
        result["errors"].append("database_or_queue_stats_unavailable")
    return result


def inventory():
    result = {
        "time": time.time(),
        "scope": "isolated-local-docker",
        "host_cores": psutil.cpu_count(),
        "host_memory_bytes": psutil.virtual_memory().total,
    }
    for key, args in {
        "docker": ["docker", "version", "--format", "{{.Server.Version}}"],
        "docker_resources": [
            "docker",
            "info",
            "--format",
            '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}}}',
        ],
        "revision": ["git", "-C", str(ROOT.parent.parent), "rev-parse", "HEAD"],
        "images": COMPOSE + ["images", "--format", "json"],
        "containers": COMPOSE + ["ps", "--format", "json"],
        "runtime": COMPOSE
        + [
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "import json,os,sys,django;django.setup();from django.conf import settings;from importlib.metadata import version;"
            "print(json.dumps({'python':sys.version,'packages':{p:version(p) for p in ['Django','gunicorn','celery','redis','psycopg']},"
            "'gunicorn_workers':os.environ.get('WEB_CONCURRENCY'),'gunicorn_threads':os.environ.get('GUNICORN_THREADS'),"
            "'api_cache_enabled':settings.API_CACHE_ENABLED,'db_conn_max_age':settings.DATABASES['default'].get('CONN_MAX_AGE'),"
            "'celery_eager':settings.CELERY_TASK_ALWAYS_EAGER,'task_soft_limit':settings.CELERY_TASK_SOFT_TIME_LIMIT,'task_hard_limit':settings.CELERY_TASK_TIME_LIMIT}))",
        ],
    }.items():
        try:
            result[key] = command(args).strip()
        except subprocess.SubprocessError:
            result[key] = "unavailable"
    result["production_parity"] = "unverified"
    try:
        ids = command(COMPOSE + ["ps", "--all", "--quiet"]).split()
        result["container_limits"] = (
            command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"name":{{json .Name}},"image":{{json .Image}},"memory_bytes":{{.HostConfig.Memory}},"nano_cpus":{{.HostConfig.NanoCpus}},"pids_limit":{{json .HostConfig.PidsLimit}}}',
                ]
                + ids
            ).strip()
            if ids
            else "no_containers"
        )
    except subprocess.SubprocessError:
        result["container_limits"] = "unavailable"
    return result
