"""AV Converter 다국어 텍스트 로그 렌더러 모듈.

단일 로그 이벤트 포맷팅, 동일 타임스탬프 들여쓰기 정렬, 동적 언어 전환 시
로그 히스토리 일괄 재렌더링(Redraw) 및 시작 시점 환경 검사(.NET, FFmpeg,
UsmToolkit, vgmstream) 보고 기능 등 전담.
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.queue_events import LogEvent

if TYPE_CHECKING:
    from .logic import ConversionLogic, FFmpegDownloader


class AVLogRenderer:
    """AV Converter의 로그 메시지 포맷팅 및 ScrolledText 위젯 렌더링 전담 클래스.

    다국어 템플릿 보간, 타임스탬프 접두사 처리, 다중 라인 들여쓰기 정렬,
    런타임 언어 변경 시 로그 재출력 및 초기 툴체인 진단 로그 생성 담당.

    Attributes:
        _get_lang_data (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _add_log_entry (Callable[..., None]): 단일 로그 큐 전송 콜백.
        _add_spacing (Callable[..., None]): 빈 줄 추가 콜백.
        _log_queue (queue.Queue[LogEvent]): 실시간 로그 이벤트 큐.
        _logic (ConversionLogic): 상대 경로 계산 및 환경 조회를 위한 비즈니스 로직 인스턴스.
        _get_tool_paths (Callable[[], dict[str, Path | None]]): 툴체인 경로 맵 콜백.
        _get_ffmpeg_downloader (Callable[[], FFmpegDownloader]): FFmpeg 다운로더 인스턴스 콜백.
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
        shared_state: Any = None,
    ) -> None:
        """AVLogRenderer 초기화.

        Args:
            get_lang_data (Callable[[], dict[str, str]]): 현재 언어 딕셔너리 반환 콜백.
            add_log_entry (Callable[..., None]): 로그 이벤트를 큐에 추가하는 콜백.
            add_spacing (Callable[..., None]): 로그 위젯에 빈 줄을 추가하는 콜백.
            log_queue (queue.Queue[LogEvent]): 로그 이벤트 큐.
            logic (ConversionLogic): ConversionLogic 인스턴스.
            get_tool_paths (Callable[[], dict[str, Path | None]]): 도구 경로 딕셔너리 반환 콜백.
            get_ffmpeg_downloader (Callable[[], FFmpegDownloader]): FFmpegDownloader 반환 콜백.
            shared_state (Any): 상위 상태 컨테이너 (선택 사항).
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
            if timestamp != last_ts:
                first_line_prefix = f"[{timestamp}] "
            else:
                first_line_prefix = " " * 13
            subsequent_line_prefix = " " * 13

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
        log_configs: list[tuple[str, list, Any]],
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
            block_ts_map: dict[Any, Any] = {}
            for i, (timestamp, key, kwargs) in enumerate(history_list):
                if timestamp:
                    if i > 0 and timestamp == history_list[i-1][0] and key != 'raw' and history_list[i-1][1] != 'raw':
                         render_ts = timestamp
                         last_ts_for_render = block_ts_map.get((timestamp, key), timestamp)
                    else:
                         render_ts = timestamp
                         last_ts_for_render = last_ts
                         block_ts_map[(timestamp, key)] = timestamp
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
        """도구 경로 찾기 결과를 로그로 출력.

        Args:
            tab: 로그를 출력할 탭 ('video' 또는 'audio').
            tool_path: 도구 파일 경로 객체 또는 None.
            tool_name: 도구의 식별용 이름.
            error_desc_key: 실패 시 출력할 에러 설명 다국어 키.
        """
        if tool_path:
            self._add_log_entry(tab, 'env_success', tool_name=tool_name)
            self._add_log_entry(tab, 'env_path', path=self._logic.get_relative_path(tool_path))
        else:
            self._add_log_entry(tab, 'env_error', tool_name=tool_name)
            self._add_log_entry(tab, error_desc_key)

    def log_initial_status(self) -> None:
        """프로그램 시작 시 초기 환경 검사 상태 로그 출력."""
        tool_paths = self._get_tool_paths()
        usmtoolkit_path = tool_paths.get('usmtoolkit')
        vgmstream_path = tool_paths.get('vgmstream')

        for tab in ['video', 'audio']:
            self._add_log_entry(tab, 'program_started')
            self._log_queue.put(LogEvent(target=tab, key='raw', un_timestamped=True, kwargs={'text': ""}))

        self._add_log_entry('video', 'env_check_header')

        dotnet_versions = self._logic.get_installed_dotnet_runtimes()
        if dotnet_versions:
            self._add_log_entry('video', 'env_success', tool_name=".NET Runtime")
            for ver in dotnet_versions:
                self._add_log_entry('video', 'env_dotnet_version', version=ver)
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
