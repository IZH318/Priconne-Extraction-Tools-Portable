"""AV Converter 다국어 텍스트 로그 렌더러 모듈.

단일 로그 이벤트 포맷팅, 동일 타임스탬프 들여쓰기 정렬, 동적 언어 전환 시
로그 히스토리 일괄 재렌더링(Redraw) 및 초기 환경 점검 로그 출력 담당.
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.queue_events import LogEvent
from src.utils.log_history import LOG_INDENT, timestamp_prefix

if TYPE_CHECKING:
    from .logic import ConversionLogic, FFmpegDownloader


class AVLogRenderer:
    """AV Converter의 로그 메시지 포맷팅 및 ScrolledText 위젯 렌더링 클래스.

    다국어 템플릿 보간, 타임스탬프 접두사 처리, 다중 라인 들여쓰기 정렬, 런타임
    언어 변경 시 로그 재출력 및 초기 환경 점검 로그 출력 담당.

    Note:
        Controller와의 순환 참조를 방지하기 위해, Controller 전체를 참조하지 않고
        필요한 콜백과 데이터 접근자만 개별 인자로 주입받습니다.

    Attributes:
        _get_lang_data (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _add_log_entry (Callable[..., None]): 로그 이벤트 큐 전달 콜백.
        _add_spacing (Callable[..., None]): 로그 빈 줄 추가 콜백.
        _log_queue (queue.Queue[LogEvent]): 타임스탬프 미표기 로그 직접 전달용 큐.
        _logic (ConversionLogic): 경로 변환·.NET Runtime 조회용 변환 로직 인스턴스.
        _get_tool_paths (Callable[[], dict[str, Path | None]]): 도구 경로 사전 조회 콜백.
        _get_ffmpeg_downloader (Callable[[], FFmpegDownloader]): FFmpeg 다운로더 조회 콜백.
    """

    def __init__(
        self,
        get_lang_data: Callable[[], dict[str, str]],
        add_log_entry: Callable[..., None],
        add_spacing: Callable[..., None],
        log_queue: queue.Queue[LogEvent],
        logic: ConversionLogic,
        get_tool_paths: Callable[[], dict[str, Path | None]],
        get_ffmpeg_downloader: Callable[[], FFmpegDownloader],
    ) -> None:
        """AVLogRenderer 초기화.

        Args:
            get_lang_data (Callable[[], dict[str, str]]): 현재 언어 딕셔너리 반환 콜백.
            add_log_entry (Callable[..., None]): 로그 이벤트를 큐에 전달하는 콜백.
            add_spacing (Callable[..., None]): 로그 빈 줄을 추가하는 콜백.
            log_queue (queue.Queue[LogEvent]): 타임스탬프 없는 원시 로그 전달용 큐 참조.
            logic (ConversionLogic): 경로 변환 및 .NET Runtime 조회용 변환 로직.
            get_tool_paths (Callable[[], dict[str, Path | None]]): 도구 경로 사전 반환 콜백.
            get_ffmpeg_downloader (Callable[[], FFmpegDownloader]): FFmpeg 다운로더 반환 콜백.
        """
        self._get_lang_data = get_lang_data
        self._add_log_entry = add_log_entry
        self._add_spacing = add_spacing
        self._log_queue = log_queue
        self._logic = logic
        self._get_tool_paths = get_tool_paths
        self._get_ffmpeg_downloader = get_ffmpeg_downloader

    def render_log_entry(self, timestamp: str | None, key: str, kwargs: dict[str, Any], last_ts: str | None = None) -> str:
        """단일 로그 이벤트를 현재 언어 설정에 맞춰 문자열로 포매팅.

        Args:
            timestamp: 로그 이벤트의 타임스탬프 문자열.
            key: 다국어 딕셔너리의 로그 메시지 키.
            kwargs: 메시지 포매팅에 사용할 인자 딕셔너리.
            last_ts: 이전에 출력된 로그의 타임스탬프 (중복 출력 방지용).

        Returns:
            포매팅된 로그 문자열.
        """
        lang_data = self._get_lang_data()

        if key == 'spacing':
            return "\n"

        content = ""
        if key == 'raw':
            content = kwargs.get('text', '')
        elif key == 'about_header':
            content = lang_data.get(key, '[ Program Information ]') + '\n'
        elif key == 'about_line_key':
            label_key = kwargs.get('label_key')
            label = lang_data.get(str(label_key) if label_key is not None else '', label_key) if label_key is not None else label_key
            value = kwargs.get('value', '')
            template = lang_data.get('about_line', "  - {label}\t: {value}")
            try:
                content = template.format(label=label, value=value)
            except (KeyError, TypeError, ValueError, IndexError):
                content = f"  - {label}\t: {value}"
        else:
            template = lang_data.get(key, "")
            if template:
                try:
                    content = template.format(**kwargs)
                except (KeyError, TypeError) as e:
                    content = f"<{key}: formatting error {e}>"
            else:
                content = f"<{key} not found in language data>"

        first_line_prefix = ""
        subsequent_line_prefix = ""
        if timestamp:
            first_line_prefix = timestamp_prefix(timestamp, timestamp == last_ts)
            subsequent_line_prefix = LOG_INDENT

        lines = content.splitlines()
        if not lines:
            if key not in ('about_line_key'):
                return first_line_prefix.rstrip() + '\n'
            else:
                return first_line_prefix.rstrip()

        processed_lines = [f"{first_line_prefix}{lines[0]}"]
        processed_lines.extend([f"{subsequent_line_prefix}{line}" for line in lines[1:]])

        final_message = '\n'.join(processed_lines)
        return final_message + '\n'

    def redraw_logs(
        self,
        log_configs: list[tuple[str, list[Any], Any]],
        last_log_timestamp: dict[str, str | None],
    ) -> None:
        """언어 변경 시 전체 로그 히스토리를 순회하며 로그 위젯 재출력.

        Args:
            log_configs: (탭이름, 히스토리리스트, 로그위젯) 튜플 리스트.
            last_log_timestamp: 탭별 마지막 타임스탬프 딕셔너리 (in-place 수정).
        """
        for tab, history_list, log_widget in log_configs:
            log_widget.config(state=tk.NORMAL)
            log_widget.delete('1.0', tk.END)
            last_ts = None

            # 동일 타임스탬프 블록 내 중복 표시 억제 처리:
            # 연속된 항목이 동일 타임스탬프를 가지면 첫 항목만 타임스탬프를 표시하고 나머지는 들여쓰기 적용
            for i, (timestamp, key, kwargs) in enumerate(history_list):
                if timestamp:
                    render_ts = timestamp
                    if i > 0 and timestamp == history_list[i-1][0] and key != 'raw' and history_list[i-1][1] != 'raw':
                        last_ts_for_render = timestamp
                    else:
                        last_ts_for_render = last_ts
                else:
                    render_ts = None
                    last_ts_for_render = last_ts

                message = self.render_log_entry(render_ts, key, kwargs, last_ts_for_render)
                log_widget.insert(tk.END, message)

                if render_ts:
                    last_ts = render_ts

            last_log_timestamp[tab] = last_ts
            log_widget.config(state=tk.DISABLED)
            log_widget.see(tk.END)

    def log_tool_status(self, tab: str, tool_path: Path | None, tool_name: str, error_desc_key: str) -> None:
        """도구 경로 탐색 결과를 환경 점검 로그로 출력.

        Args:
            tab: 로그를 출력할 탭 ('video' 또는 'audio').
            tool_path: 도구 파일 경로 객체 또는 None.
            tool_name: 도구 식별용 표시 이름.
            error_desc_key: 도구 미발견 시 출력할 에러 설명 다국어 키.
        """
        if tool_path:
            self._add_log_entry(tab, 'env_success', tool_name=tool_name)
            self._add_log_entry(tab, 'env_path', path=self._logic.get_relative_path(tool_path))
        else:
            self._add_log_entry(tab, 'env_error', tool_name=tool_name)
            self._add_log_entry(tab, error_desc_key)

    @staticmethod
    def _format_runtime_versions(entries: list[str]) -> str:
        """'Microsoft.NETCore.App <version>' 목록에서 버전 문자열만 콤마로 이어붙여 반환."""
        return ", ".join(entry.split()[-1] for entry in entries)

    def log_initial_status(self) -> None:
        """프로그램 시작 시 초기 환경 점검 상태를 비디오/오디오 탭 로그로 출력."""
        tool_paths = self._get_tool_paths()
        usmtoolkit_path = tool_paths.get('usmtoolkit')
        vgmstream_path = tool_paths.get('vgmstream')

        for tab in ['video', 'audio']:
            self._add_log_entry(tab, 'program_started')
            self._log_queue.put(LogEvent(target=tab, key='raw', un_timestamped=True, kwargs={'text': ""}))

        self._add_log_entry('video', 'env_check_header')

        by_source = self._logic.get_dotnet_runtimes_by_source()
        local_versions = by_source.get("local", [])
        system_versions = by_source.get("system", [])
        if local_versions or system_versions:
            self._add_log_entry('video', 'env_success', tool_name=".NET Runtime")
            if local_versions:
                self._add_log_entry('video', 'env_dotnet_local', versions=self._format_runtime_versions(local_versions))
            if system_versions:
                self._add_log_entry('video', 'env_dotnet_system', versions=self._format_runtime_versions(system_versions))
        else:
            self._add_log_entry('video', 'env_error', tool_name=".NET Runtime")
            self._add_log_entry('video', 'env_error_desc_dotnet')

        self.log_tool_status('video', usmtoolkit_path, "UsmToolkit.exe", 'env_error_desc_video')
        ffmpeg_downloader = self._get_ffmpeg_downloader()
        ffmpeg_path = ffmpeg_downloader.ffmpeg_path if ffmpeg_downloader.ffmpeg_path.exists() else None
        self.log_tool_status('video', ffmpeg_path, "FFmpeg (ffmpeg.exe)", 'env_error_desc_ffmpeg_auto_download')
        self._add_log_entry('video', 'max_worker_log', count=self._logic.MAX_WORKERS)
        self._add_spacing('video')

        self._add_log_entry('audio', 'env_check_header')
        self.log_tool_status('audio', vgmstream_path, "vgmstream(vgmstream-cli.exe)", 'env_error_desc_audio')
        self._add_log_entry('audio', 'max_worker_log', count=self._logic.MAX_WORKERS)
        self._add_spacing('audio')
