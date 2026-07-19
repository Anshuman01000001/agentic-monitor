import psutil
from typing import Dict, Any


def collect_device_metrics() -> Dict[str, Any]:
    """Collect a small set of device metrics and return as a dict."""
    metrics = {}
    metrics["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    metrics["per_core_percent"] = psutil.cpu_percent(interval=0.0, percpu=True)
    vm = psutil.virtual_memory()
    metrics["memory_percent"] = vm.percent
    metrics["memory_available_mb"] = vm.available / (1024 * 1024)
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({"mountpoint": part.mountpoint, "percent": usage.percent})
        except Exception:
            continue
    metrics["disks"] = disks
    net = psutil.net_io_counters()
    metrics["net_bytes_sent"] = net.bytes_sent
    metrics["net_bytes_recv"] = net.bytes_recv
    # top 5 processes by CPU
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            procs.append(p.info)
        except Exception:
            continue
    procs = sorted(procs, key=lambda x: x.get("cpu_percent", 0), reverse=True)[:5]
    metrics["top_processes"] = procs
    return metrics
