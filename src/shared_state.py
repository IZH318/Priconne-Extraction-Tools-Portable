"""서비스 및 컨트롤러 간 공유 상태 및 콜백 번들(Parameter Object) 모듈.

다수 콜백 함수와 큐 인스턴스를 서비스 생성자에 개별 주입 시 발생하는
파라미터 폭발(Long Parameter List) 안티패턴 해소를 위해,
상태 및 콜백을 응집력 있게 묶어 전달하는 SharedState 데이터클래스 제공.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SharedState:
    """서비스 계층과 컨트롤러 계층 간 공유 상태 및 콜백 캡슐화 매개변수 객체.

    개별 콜백 전달 대신 단일 상태 객체 주입으로 생성자 시그니처 단순화.
    """

    # 공통 콜백 및 프로바이더
    get_lang_dict: Callable[[], dict[str, str]] = field(default=lambda: {})
    add_log_entry: Callable[..., None] = field(default=lambda *a, **k: None)
    add_spacing: Callable[..., None] = field(default=lambda *a, **k: None)
    get_base_path: Callable[[], Any] = field(default=lambda: None)
    get_view: Callable[[], Any] = field(default=lambda: None)

    # AV Converter 전용 콜백 및 상태 접근자
    get_lang_data: Callable[[], dict[str, str]] = field(default=lambda: {})
    get_video_full_paths: Callable[[], list[str]] = field(default=lambda: [])
    get_audio_full_paths: Callable[[], list[str]] = field(default=lambda: [])
    get_usmtoolkit_path: Callable[[], Any] = field(default=lambda: None)
    set_usmtoolkit_path: Callable[[Any], None] = field(default=lambda *a, **k: None)
    get_vgmstream_path: Callable[[], Any] = field(default=lambda: None)
    set_vgmstream_path: Callable[[Any], None] = field(default=lambda *a, **k: None)
    get_video_cancel_token: Callable[[], Any] = field(default=lambda: None)
    get_audio_cancel_token: Callable[[], Any] = field(default=lambda: None)
    start_tool_preparation: Callable[..., None] = field(default=lambda *a, **k: None)
    set_conversion_thread: Callable[[Any, Any], None] = field(default=lambda *a, **k: None)
    resume_polling: Callable[[], None] = field(default=lambda *a, **k: None)
    is_dotnet_runtime_available: Callable[[], bool] = field(default=lambda: False)
    get_converting_state: Callable[..., bool] = field(default=lambda *a, **k: False)
    set_ui_state: Callable[..., None] = field(default=lambda *a, **k: None)
    reset_ui_state: Callable[..., None] = field(default=lambda *a, **k: None)
    get_video_total_files: Callable[[], int] = field(default=lambda: 0)
    set_video_total_files: Callable[[int], None] = field(default=lambda *a, **k: None)
    get_audio_total_files: Callable[[], int] = field(default=lambda: 0)
    set_audio_total_files: Callable[[int], None] = field(default=lambda *a, **k: None)
    get_video_widgets: Callable[[], dict] = field(default=lambda: {})
    get_audio_widgets: Callable[[], dict] = field(default=lambda: {})
    get_tool_paths: Callable[[], dict] = field(default=lambda: {})
    get_ffmpeg_downloader: Callable[[], Any] = field(default=lambda: None)
    get_paths: Callable[[Any], list[str]] = field(default=lambda *a, **k: [])
    find_tools: Callable[[], None] = field(default=lambda *a, **k: None)
    tool_pipeline: Any = None
    preview_selected_fn: Callable[[Any, Any], None] = field(default=lambda *a, **k: None)
    logic: Any = None
    preview_temp_dir: Any = None
    generate_error_log: Callable[[str, list], None] = field(default=lambda *a, **k: None)
    prepare_tools: Callable[[Any, Any], None] = field(default=lambda *a, **k: None)

    # Manifest File Renamer 전용 콜백 및 큐
    get_string: Callable[..., str] = field(default=lambda *a, **k: "")
    log_queue: Any = None
    progress_queue: Any = None
    base_path_provider: Callable[[], Any] = field(default=lambda: None)

