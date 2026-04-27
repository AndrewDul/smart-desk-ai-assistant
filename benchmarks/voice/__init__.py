"""Voice benchmark package for NEXA Voice Engine v2.

Keep this package initializer lightweight.

Do not import benchmark modules here. The benchmark modules are designed to be
runnable with `python -m benchmarks.voice.<module>`, and eager imports from this
file can cause runpy warnings because the module is already present in
sys.modules before execution.
"""

__all__ = [
    "benchmark_command_latency",
    "benchmark_endpointing_latency",
    "benchmark_full_voice_turn",
]