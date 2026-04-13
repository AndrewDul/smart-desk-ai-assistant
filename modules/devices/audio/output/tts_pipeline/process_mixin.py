from __future__ import annotations

import shlex
import subprocess
import time
from typing import Any

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

    @staticmethod
    def _truncate_process_output(text: str, *, limit: int = 600) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rstrip() + " ..."

    @staticmethod
    def _format_process_command(args: list[str]) -> str:
        try:
            return shlex.join([str(item) for item in args])
        except Exception:
            return " ".join(str(item) for item in args)

    def _remember_process_result(
        self,
        *,
        source: str,
        command: list[str],
        success: bool,
        return_code: int | None,
        elapsed_seconds: float,
        stdout_text: str,
        stderr_text: str,
        timed_out: bool = False,
        interrupted: bool = False,
        error_text: str = "",
    ) -> None:
        result = {
            "source": str(source),
            "command": list(command),
            "command_display": self._format_process_command(command),
            "success": bool(success),
            "return_code": return_code,
            "elapsed_seconds": float(elapsed_seconds),
            "stdout_text": str(stdout_text or ""),
            "stderr_text": str(stderr_text or ""),
            "timed_out": bool(timed_out),
            "interrupted": bool(interrupted),
            "error_text": str(error_text or ""),
        }
        with self._process_lock:
            self._last_process_results[str(source)] = result

    def _get_last_process_result(self, source: str) -> dict[str, Any]:
        with self._process_lock:
            result = self._last_process_results.get(str(source), {})
        return dict(result)

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
        stdout_text = ""
        stderr_text = ""
        timed_out = False
        interrupted = False
        error_text = ""

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
                    interrupted = True
                    self._terminate_process(process, reason=source)
                    break

                return_code = process.poll()
                if return_code is not None:
                    break

                if (time.monotonic() - started_at) >= timeout_seconds:
                    timed_out = True
                    append_log(f"{source} process timed out after {timeout_seconds:.2f}s.")
                    self._terminate_process(process, reason=f"{source}_timeout")
                    break

                time.sleep(0.02)

            if process.stdout is not None:
                try:
                    stdout_text = process.stdout.read()
                except Exception:
                    stdout_text = ""

            if process.stderr is not None:
                try:
                    stderr_text = process.stderr.read()
                except Exception:
                    stderr_text = ""

            return_code = process.poll()
            success = bool(return_code == 0 and not timed_out and not interrupted)

            elapsed_seconds = time.monotonic() - started_at
            self._remember_process_result(
                source=source,
                command=args,
                success=success,
                return_code=return_code,
                elapsed_seconds=elapsed_seconds,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                timed_out=timed_out,
                interrupted=interrupted,
                error_text=error_text,
            )

            if not success:
                append_log(
                    f"{source} process failed: "
                    f"exit_code={return_code}, "
                    f"timed_out={timed_out}, "
                    f"interrupted={interrupted}, "
                    f"elapsed={elapsed_seconds:.3f}s, "
                    f"command={self._format_process_command(args)}"
                )
                stderr_preview = self._truncate_process_output(stderr_text)
                stdout_preview = self._truncate_process_output(stdout_text)
                if stderr_preview:
                    append_log(f"{source} stderr: {stderr_preview}")
                elif stdout_preview:
                    append_log(f"{source} stdout: {stdout_preview}")

            return success
        except Exception as error:
            error_text = str(error)
            append_log(f"{source} process error: {error_text}")
            self._remember_process_result(
                source=source,
                command=args,
                success=False,
                return_code=None,
                elapsed_seconds=time.monotonic() - started_at,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                timed_out=timed_out,
                interrupted=interrupted,
                error_text=error_text,
            )
            return False
        finally:
            if process is not None:
                self._unregister_process(process)


__all__ = ["TTSPipelineProcessMixin"]