from __future__ import annotations

import subprocess
import time

from modules.system.utils import append_log


class TTSPipelineProcessMixin:
    """
    Helpers for tracking, terminating, and running subprocesses safely.
    """

    def _register_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            self._active_processes.append(process)

    def _unregister_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            self._active_processes = [
                item for item in self._active_processes if item is not process
            ]

    @staticmethod
    def _terminate_process(process: subprocess.Popen, *, reason: str) -> None:
        try:
            if process.poll() is not None:
                return

            process.terminate()
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.25)
        except Exception as error:
            append_log(f"TTS process termination warning ({reason}): {error}")

    def _run_process_interruptibly(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float,
        source: str,
    ) -> bool:
        started_at = time.monotonic()
        process: subprocess.Popen | None = None

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._register_process(process)

            if input_text is not None and process.stdin is not None:
                try:
                    process.stdin.write(input_text)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                except Exception as error:
                    append_log(f"{source} stdin warning: {error}")

            while True:
                if self._stop_requested.is_set():
                    self._terminate_process(process, reason=source)
                    return False

                return_code = process.poll()
                if return_code is not None:
                    return return_code == 0

                if (time.monotonic() - started_at) >= timeout_seconds:
                    append_log(f"{source} process timed out after {timeout_seconds:.2f}s.")
                    self._terminate_process(process, reason=f"{source}_timeout")
                    return False

                time.sleep(0.02)
        except Exception as error:
            append_log(f"{source} process error: {error}")
            return False
        finally:
            if process is not None:
                self._unregister_process(process)


__all__ = ["TTSPipelineProcessMixin"]