"""Post-process orchestration — file I/O, logging, run loop."""
from __future__ import annotations

import abc

import time
from pathlib import Path

from gcode_checks import (
    GcodeAnalysis,
    analysis_for_state,
    analyze_gcode,
    gcode_stats,
    is_postprocessed,
    path_hint,
    validate_text,
)
from gcode_export import find_recent_export, path_note
from gcode_patterns import strip_pp_lines
from gcode_transform import transform_gcode
from log_util import log, write_state
from profile import parse_prusa_config


class ILogger(abc.ABC):
    @abc.abstractmethod
    def log_result(self, event: str, note: str, errors: list[str], warnings: list[str], text: str, quiet: bool, extra: list[str] | None = None, analysis: GcodeAnalysis | None = None) -> None:
        pass


class DefaultLogger(ILogger):
    def _summarize_actions(self, actions: list[str]) -> str:
        if not actions:
            return "none"
        counts: dict[str, int] = {}
        order: list[str] = []
        for action in actions:
            if action not in counts:
                order.append(action)
                counts[action] = 0
            counts[action] += 1
        return "[" + ", ".join(f"{a}×{counts[a]}" if counts[a] > 1 else a for a in order) + "]"

    def log_result(
        self,
        event: str,
        note: str,
        errors: list[str],
        warnings: list[str],
        text: str,
        quiet: bool,
        extra: list[str] | None = None,
        analysis: GcodeAnalysis | None = None,
    ) -> None:
        parts = [note, f"stats={gcode_stats(text, analysis=analysis)}"] + (extra or [])
        if warnings:
            parts.append(f"warnings={warnings}")
        if errors:
            parts.append(f"errors={errors}")
        label = event if event.endswith("SKIP") else f"{event} {'FAIL' if errors else ('WARN' if warnings else 'OK')}"
        log(label, " | ".join(parts), echo=not quiet)

    def log_state_warn(self, msg: str, quiet: bool) -> None:
        if not quiet:
            log("STATE WARN", msg)

    def log_fail(self, note: str, quiet: bool) -> None:
        log("POSTPROCESS FAIL", note, echo=not quiet)


class PostProcessApp:
    def __init__(self, logger: ILogger | None = None):
        self.logger = logger or DefaultLogger()

    def run(self, paths: list[Path], quiet: bool = False, force: bool = False, argv: list[str] | None = None) -> int:
        code = 0
        logger = self.logger
        if not isinstance(logger, DefaultLogger):
            # Fallback for duck typing if needed, but we assume DefaultLogger methods for now
            pass
            
        for path in paths:
            start = time.monotonic()
            if not path.is_file():
                if isinstance(logger, DefaultLogger):
                    logger.log_fail(f"{path} | file not found", quiet)
                code = 1
                continue

            raw = path.read_text(encoding="utf-8", errors="replace")
            hint = path_hint(path)

            if is_postprocessed(raw) and not force:
                analysis = analyze_gcode(raw, hint)
                errors, warnings = validate_text(raw, expect_postprocess=True, analysis=analysis)
                logger.log_result(
                    "POSTPROCESS SKIP",
                    path_note(path, argv),
                    errors,
                    warnings,
                    raw,
                    quiet,
                    ["skipped=already_processed"],
                    analysis,
                )
                code |= bool(errors)
                continue

            analysis = analyze_gcode(raw, hint)
            prusa_cfg = parse_prusa_config(raw)
            need_sup = analysis["needs_support"]
            skip_overhang_fan = (
                analysis["large"] and analysis["overhang_markers"] > 40 and not need_sup
            )
            new_lines, actions = transform_gcode(
                strip_pp_lines(raw.splitlines(), full=force),
                skip_overhang_fan=skip_overhang_fan,
                prusa_cfg=prusa_cfg,
            )
            if skip_overhang_fan:
                actions.append(f"fan_overhang_skip×{analysis['overhang_markers']}")
            elif need_sup:
                actions.append("support_cooling")

            result = "\n".join(new_lines) + "\n"
            path.write_text(result, encoding="utf-8")

            export = None
            try:
                export = find_recent_export()
                hint = path_hint(path, export)
            except OSError as e:
                if isinstance(logger, DefaultLogger):
                    logger.log_state_warn(str(e), quiet)

            result_analysis = analyze_gcode(result, hint)
            errors, warnings = validate_text(result, expect_postprocess=True, analysis=result_analysis)
            try:
                write_state(analysis_for_state(result_analysis, last_path=str(path), last_export=str(export or "")))
            except OSError as e:
                if isinstance(logger, DefaultLogger):
                    logger.log_state_warn(str(e), quiet)

            extra = [
                f"slicer={result_analysis['slicer_time'] or '?'}",
                f"pp={int((time.monotonic() - start) * 1000)}ms",
                f"{path.stat().st_size // 1024}KB",
            ]
            if isinstance(logger, DefaultLogger):
                extra.insert(1, f"actions={logger._summarize_actions(actions)}")

            logger.log_result(
                "POSTPROCESS",
                path_note(path, argv, export),
                errors,
                warnings,
                result,
                quiet,
                extra,
                result_analysis,
            )
            code |= bool(errors)
        return code


def run_postprocess(
    paths: list[Path],
    quiet: bool = False,
    force: bool = False,
    argv: list[str] | None = None,
) -> int:
    app = PostProcessApp()
    return app.run(paths, quiet, force, argv)
