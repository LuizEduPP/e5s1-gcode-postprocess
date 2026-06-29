"""Post-process orchestration — file I/O, logging, run loop."""
from __future__ import annotations

import abc

import time
from pathlib import Path

from gcode_checks import (
    GcodeAnalysis,
    GCodeAnalyzer,
    GCodeValidator,
    IGCodeAnalyzer,
    IGCodeValidator,
)
from gcode_export import IExportFinder, RecentExportFinder
from gcode_patterns import IGCodePatternMatcher, GCodePatternMatcher
from gcode_transform import transform_gcode
from log_util import IStateLogger, LoggerFactory
from profile import parse_prusa_config


class ILogger(abc.ABC):
    @abc.abstractmethod
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
        pass

    @abc.abstractmethod
    def log_state_warn(self, msg: str, quiet: bool) -> None:
        pass

    @abc.abstractmethod
    def log_fail(self, note: str, quiet: bool) -> None:
        pass

    @abc.abstractmethod
    def format_actions(self, actions: list[str]) -> str:
        pass


class DefaultLogger(ILogger):
    def __init__(self, state_logger: IStateLogger, analyzer: IGCodeAnalyzer):
        self.state_logger = state_logger
        self.analyzer = analyzer
    def format_actions(self, actions: list[str]) -> str:
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
        parts = [note, f"stats={self.analyzer.get_stats(text, analysis=analysis)}"] + (extra or [])
        if warnings:
            parts.append(f"warnings={warnings}")
        if errors:
            parts.append(f"errors={errors}")
        label = event if event.endswith("SKIP") else f"{event} {'FAIL' if errors else ('WARN' if warnings else 'OK')}"
        self.state_logger.log(label, " | ".join(parts), echo=not quiet)

    def log_state_warn(self, msg: str, quiet: bool) -> None:
        if not quiet:
            self.state_logger.log("STATE WARN", msg)

    def log_fail(self, note: str, quiet: bool) -> None:
        self.state_logger.log("POSTPROCESS FAIL", note, echo=not quiet)


class PostProcessApp:
    def __init__(
        self,
        logger: ILogger | None = None,
        analyzer: IGCodeAnalyzer | None = None,
        validator: IGCodeValidator | None = None,
        export_finder: IExportFinder | None = None,
        pattern_matcher: IGCodePatternMatcher | None = None,
        state_logger: IStateLogger | None = None,
    ):
        self.analyzer = analyzer or GCodeAnalyzer()
        self.validator = validator or GCodeValidator(self.analyzer)
        self.export_finder = export_finder or RecentExportFinder()
        self.pattern_matcher = pattern_matcher or GCodePatternMatcher()
        self.state_logger = state_logger or LoggerFactory.get_instance()
        
        if logger is None:
            self.logger = DefaultLogger(self.state_logger, self.analyzer)
        else:
            self.logger = logger

    def run(self, paths: list[Path], quiet: bool = False, force: bool = False, argv: list[str] | None = None) -> int:
        code = 0
            
        for path in paths:
            start = time.monotonic()
            if not path.is_file():
                self.logger.log_fail(f"{path} | file not found", quiet)
                code = 1
                continue

            raw = path.read_text(encoding="utf-8", errors="replace")
            hint = " ".join(str(p) for p in [path] if p)

            if MARKER in raw and not force:
                analysis = self.analyzer.analyze(raw, hint)
                errors, warnings = self.validator.validate(raw, expect_postprocess=True, analysis=analysis)
                self.logger.log_result(
                    "POSTPROCESS SKIP",
                    self.export_finder.path_note(path, argv),
                    errors,
                    warnings,
                    raw,
                    quiet,
                    ["skipped=already_processed"],
                    analysis,
                )
                code |= bool(errors)
                continue

            analysis = self.analyzer.analyze(raw, hint)
            prusa_cfg = parse_prusa_config(raw)
            need_sup = analysis["needs_support"]
            skip_overhang_fan = (
                analysis["large"] and analysis["overhang_markers"] > 40 and not need_sup
            )
            new_lines, actions = transform_gcode(
                self.pattern_matcher.strip_pp_lines(raw.splitlines(), full=force),
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
                export = self.export_finder.find_recent_export()
                hint = " ".join(str(p) for p in [path, export] if p)
            except OSError as e:
                self.logger.log_state_warn(str(e), quiet)

            result_analysis = self.analyzer.analyze(result, hint)
            errors, warnings = self.validator.validate(result, expect_postprocess=True, analysis=result_analysis)
            try:
                state_data = {
                    **{k: v for k, v in result_analysis.items() if v is not None and k != "large"},
                    "last_path": str(path),
                    "last_export": str(export or "")
                }
                self.state_logger.write_state(state_data)
            except OSError as e:
                self.logger.log_state_warn(str(e), quiet)

            extra = [
                f"slicer={result_analysis['slicer_time'] or '?'}",
                f"actions={self.logger.format_actions(actions)}",
                f"pp={int((time.monotonic() - start) * 1000)}ms",
                f"{path.stat().st_size // 1024}KB",
            ]

            self.logger.log_result(
                "POSTPROCESS",
                self.export_finder.path_note(path, argv, export),
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
