# --- START OF FILE 03. Audio Video Converter.py ---

import os
import sys
import subprocess
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, Listbox, Menu
import concurrent.futures
import urllib.request
import zipfile
import shutil

# --- 다국어 텍스트 데이터 ---
LANGUAGES = {
    'ko': {
        'window_title': "오디오/비디오 변환기",
        'video_tab': "비디오 변환기 (.usm → .mp4)",
        'audio_tab': "오디오 변환기 (.awb → .wav)",
        'input_section': "1. 원본 파일/폴더 선택",
        'add_files': "파일 추가",
        'add_folder': "폴더 추가",
        'file_list_section': "파일 목록",
        'output_section': "2. 저장 경로 선택",
        'browse': "경로 지정",
        'action_section': "3. 변환 실행",
        'start_conversion': "변환 시작",
        'cancel_conversion': "변환 중단",
        'overwrite_option': "기존 파일 덮어쓰기",
        'log_section': "처리 내역",
        # 메뉴 및 정보
        'menu_language': "언어",
        'menu_info': "정보",
        'about_header': "[ 프로그램 정보 ]",
        'about_label_program': "프로그램 이름",
        'about_label_version': "버전",
        'about_label_updated': "최종 업데이트",
        'about_label_license': "라이선스",
        'about_label_developer': "개발자",
        'about_label_website': "웹 사이트",
        'about_line': "  - {label}\t: {value}",
        # 리스트박스 메뉴
        'remove_selected': "선택 항목 제거",
        'remove_all': "전체 항목 제거",
        # 메시지 및 오류
        'alert_files_exist': "[알림] 선택한 파일들은 이미 목록에 존재합니다.",
        'log_files_added': "{count}개의 새 파일이 추가되었습니다.",
        'log_total_files': "총 파일 수: {total}개",
        'log_files_removed': "{count}개의 파일이 목록에서 삭제되었습니다.",
        'log_all_files_removed': "파일 목록 전체가 삭제되었습니다. ({count}개)",
        'log_conversion_cancelled': "사용자에 의해 변환 작업이 중단되었습니다.",
        'error_no_files': "[오류] 변환할 파일을 먼저 추가하세요.",
        'error_no_output_video': "[오류] 비디오를 저장할 경로를 지정하세요.",
        'error_no_output_audio': "[오류] 오디오를 저장할 경로를 지정하세요.",
        # 상태 라벨 텍스트
        'status_idle': "상태: 대기 중",
        'status_starting': "처리 시작... (총 {total}개)",
        'status_processing': "처리중: {current} / {total}",
        'status_complete': "완료: {current} / {total}",
        'status_cancelled': "중단됨: {current} / {total}",
        # 초기 상태 로그
        'env_check_header': "--- 프로그램 환경 점검 ---",
        'env_success': "  [성공] {tool_name} 발견",
        'env_path': "    > 경로: {path}",
        'env_error': "  [오류] {tool_name}을(를) 찾을 수 없음",
        'env_error_desc_video': "    > 비디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        'env_error_desc_audio': "    > 오디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        'env_error_desc_ffmpeg_auto_download': "    > 비디오 변환 시작 시 자동으로 FFmpeg 다운로드",
        'env_check_footer': "--------------------------",
        'max_worker_log': "[시스템] 시스템 부하를 고려하여 최대 {count}개의 파일을 동시에 변환합니다.",
        # 변환 로그
        'conv_log_source': "  [원본]\n    {path}",
        'conv_log_result_header': "\n  [결과]",
        'conv_log_skipped': "    이미 변환된 파일입니다. (건너뜀)",
        'conv_log_success': "    변환 성공: {path}",
        'conv_log_error_no_file': "    [오류] 변환은 성공했으나 결과 파일이 없습니다.",
        'conv_log_error_fail': "    [오류] 변환 실패 - {filename}",
        'conv_log_error_exception': "    [오류] 치명적 예외 발생 - {error}",
        'conv_log_details_header': "\n  [상세 로그]",
        'conv_log_details_error_header': "\n  [상세 오류]",
        'conv_log_worker_exception': "  [오류] 작업자 실행 중 예외: {filename} - {error}",
        'conv_start_video': "\n--- 비디오 변환 작업을 시작합니다. ---",
        'conv_start_audio': "\n--- 오디오 변환 작업을 시작합니다. ---",
        'conv_video_skip_notice': "[알림] 기존 파일은 항상 건너뜁니다.",
        'conv_audio_overwrite_notice': "[옵션] 기존 파일을 덮어씁니다.",
        'conv_audio_skip_notice': "[옵션] 기존 파일은 건너뜁니다.",
        'conv_error_usmtoolkit_not_found': "\n[오류] UsmToolkit.exe를 찾을 수 없습니다. 변환을 중단합니다.\n",
        'conv_error_vgmstream_not_found': "\n[오류] vgmstream 실행 파일(test.exe)을 찾을 수 없습니다. 변환을 중단합니다.\n",
        'conv_complete_video': "\n--- 비디오 변환 작업이 완료되었습니다. ---",
        'conv_summary_video': "총 {total}개 파일 중 {success}개 변환, {skipped}개 건너뜀, {error}개 오류.\n",
        'conv_complete_audio': "\n--- 오디오 변환 작업이 완료되었습니다. ---",
        'conv_summary_audio': "총 {tracks}개의 트랙이 WAV 파일로 변환되었습니다.\n",
        'conv_audio_stream_error': "    [오류] 파일의 스트림 정보를 읽을 수 없습니다.",
        'conv_audio_stream_skipped': "    알림: 이미 변환된 파일 (건너뜀) - {filename}",
        'conv_audio_stream_success': "    성공: {path}",
        'conv_audio_stream_fail': "    [오류] 스트림 #{index} 변환 실패 - {name}",
        # FFmpeg 관련 메시지
        'ffmpeg_preparing': "FFmpeg 준비 중... (필요 시 다운로드)",
        'ffmpeg_not_found': "[알림] FFmpeg (ffmpeg.exe)이 발견되지 않았습니다. {path} 경로로 다운로드 및 설치를 시도합니다.",
        'ffmpeg_already_exists': "[알림] FFmpeg (ffmpeg.exe)이 {path} 경로에 이미 존재합니다. (패스)",
        'ffmpeg_download_start': "  > FFmpeg 다운로드 시작: {url}",
        'ffmpeg_download_complete': "  > FFmpeg 다운로드 완료.",
        'ffmpeg_download_fail': "[오류] FFmpeg 다운로드 실패: {error}",
        'ffmpeg_extract_start': "  > FFmpeg 압축 해제 시작...",
        'ffmpeg_extract_complete': "  > FFmpeg 압축 해제 및 설치 완료: {path}",
        'ffmpeg_extract_fail': "[오류] FFmpeg 압축 해제 및 설치 실패: {error}",
        'ffmpeg_prepare_fail': "[오류] FFmpeg이 준비되지 않아 비디오 변환을 시작할 수 없습니다.",
        'ffmpeg_no_usm_path': "[오류] UsmToolkit.exe 경로를 알 수 없어 FFmpeg을 다운로드할 위치를 결정할 수 없습니다. 변환을 중단합니다.",
        'ffmpeg_zip_structure_error': "FFmpeg ZIP 파일 내부에 예상되는 폴더 구조를 찾을 수 없습니다.",
        'ffmpeg_exe_not_found_in_zip': "압축 해제 후 '{path}'를 찾을 수 없습니다. ZIP 파일 구조를 확인해주세요.",
    },
    'en': {
        'window_title': "Audio/Video Converter",
        'video_tab': "Video Converter (.usm → .mp4)",
        'audio_tab': "Audio Converter (.awb → .wav)",
        'input_section': "1. Select Source Files/Folders",
        'add_files': "Add Files",
        'add_folder': "Add Folder",
        'file_list_section': "File List",
        'output_section': "2. Select Output Path",
        'browse': "Browse",
        'action_section': "3. Run Conversion",
        'start_conversion': "Start Conversion",
        'cancel_conversion': "Cancel Conversion",
        'overwrite_option': "Overwrite existing files",
        'log_section': "Processing Log",
        'menu_language': "Language",
        'menu_info': "Info",
        'about_header': "[ Program Information ]",
        'about_label_program': "Program Name",
        'about_label_version': "Version",
        'about_label_updated': "Last Updated",
        'about_label_license': "License",
        'about_label_developer': "Developer",
        'about_label_website': "Website",
        'about_line': "  - {label}\t: {value}",
        'remove_selected': "Remove Selected",
        'remove_all': "Remove All",
        'alert_files_exist': "[Alert] The selected files already exist in the list.",
        'log_files_added': "{count} new files have been added.",
        'log_total_files': "Total files: {total}",
        'log_files_removed': "{count} files have been removed from the list.",
        'log_all_files_removed': "The entire file list has been cleared. ({count} files)",
        'log_conversion_cancelled': "The conversion task was cancelled by the user.",
        'error_no_files': "[Error] Please add files to convert first.",
        'error_no_output_video': "[Error] Please specify a path to save the videos.",
        'error_no_output_audio': "[Error] Please specify a path to save the audios.",
        'status_idle': "Status: Idle",
        'status_starting': "Starting... (Total {total})",
        'status_processing': "Processing: {current} / {total}",
        'status_complete': "Completed: {current} / {total}",
        'status_cancelled': "Cancelled: {current} / {total}",
        'env_check_header': "--- Program Environment Check ---",
        'env_success': "  [Success] {tool_name} found",
        'env_path': "    > Path: {path}",
        'env_error': "  [Error] Could not find {tool_name}",
        'env_error_desc_video': "    > The video conversion tab may not function correctly.",
        'env_error_desc_audio': "    > The audio conversion tab may not function correctly.",
        'env_error_desc_ffmpeg_auto_download': "    > FFmpeg will be downloaded automatically when video conversion starts.",
        'env_check_footer': "-----------------------------",
        'max_worker_log': "[System] Up to {count} files will be converted simultaneously considering system load.",
        'conv_log_source': "  [Source]\n    {path}",
        'conv_log_result_header': "\n  [Result]",
        'conv_log_skipped': "    Already converted file. (Skipped)",
        'conv_log_success': "    Conversion successful: {path}",
        'conv_log_error_no_file': "    [Error] Conversion succeeded, but the output file is missing.",
        'conv_log_error_fail': "    [Error] Conversion failed - {filename}",
        'conv_log_error_exception': "    [Error] Critical exception occurred - {error}",
        'conv_log_details_header': "\n  [Details Log]",
        'conv_log_details_error_header': "\n  [Error Details]",
        'conv_log_worker_exception': "  [Error] Exception during worker execution: {filename} - {error}",
        'conv_start_video': "\n--- Starting video conversion ---",
        'conv_start_audio': "\n--- Starting audio conversion ---",
        'conv_video_skip_notice': "[Notice] Existing files are always skipped.",
        'conv_audio_overwrite_notice': "[Option] Overwriting existing files.",
        'conv_audio_skip_notice': "[Option] Skipping existing files.",
        'conv_error_usmtoolkit_not_found': "\n[Error] UsmToolkit.exe not found. Aborting conversion.\n",
        'conv_error_vgmstream_not_found': "\n[Error] vgmstream executable (test.exe) not found. Aborting conversion.\n",
        'conv_complete_video': "\n--- Video conversion complete ---",
        'conv_summary_video': "Total {total} files: {success} converted, {skipped} skipped, {error} errors.\n",
        'conv_complete_audio': "\n--- Audio conversion complete ---",
        'conv_summary_audio': "A total of {tracks} tracks have been converted to WAV files.\n",
        'conv_audio_stream_error': "    [Error] Could not read stream info from the file.",
        'conv_audio_stream_skipped': "    Notice: Already converted file (skipped) - {filename}",
        'conv_audio_stream_success': "    Success: {path}",
        'conv_audio_stream_fail': "    [Error] Stream #{index} conversion failed - {name}",
        'ffmpeg_preparing': "Preparing FFmpeg... (downloading if needed)",
        'ffmpeg_not_found': "[Alert] FFmpeg (ffmpeg.exe) not found. Attempting to download and install to {path}.",
        'ffmpeg_already_exists': "[Alert] FFmpeg (ffmpeg.exe) already exists at {path}. (Skipping)",
        'ffmpeg_download_start': "  > Starting FFmpeg download: {url}",
        'ffmpeg_download_complete': "  > FFmpeg download complete.",
        'ffmpeg_download_fail': "[Error] FFmpeg download failed: {error}",
        'ffmpeg_extract_start': "  > Starting FFmpeg extraction...",
        'ffmpeg_extract_complete': "  > FFmpeg extraction and installation complete: {path}",
        'ffmpeg_extract_fail': "[Error] FFmpeg extraction and installation failed: {error}",
        'ffmpeg_prepare_fail': "[Error] Cannot start video conversion because FFmpeg is not ready.",
        'ffmpeg_no_usm_path': "[Error] Cannot determine where to download FFmpeg because UsmToolkit.exe path is unknown. Aborting.",
        'ffmpeg_zip_structure_error': "Could not find the expected folder structure within the FFmpeg ZIP file.",
        'ffmpeg_exe_not_found_in_zip': "Could not find '{path}' after extraction. Please check the ZIP file structure.",
    },
    'ja': {
        'window_title': "オーディオ/ビデオコンバーター",
        'video_tab': "ビデオコンバーター (.usm → .mp4)",
        'audio_tab': "オーディオコンバーター (.awb → .wav)",
        'input_section': "1. 元ファイル/フォルダを選択",
        'add_files': "ファイル追加",
        'add_folder': "フォルダ追加",
        'file_list_section': "ファイル一覧",
        'output_section': "2. 保存先を選択",
        'browse': "参照",
        'action_section': "3. 変換実行",
        'start_conversion': "変換開始",
        'cancel_conversion': "変換中止",
        'overwrite_option': "既存のファイルを上書き",
        'log_section': "処理履歴",
        'menu_language': "言語",
        'menu_info': "情報",
        'about_header': "[ プログラム情報 ]",
        'about_label_program': "プログラム名",
        'about_label_version': "バージョン",
        'about_label_updated': "最終更新日",
        'about_label_license': "ライセンス",
        'about_label_developer': "開発者",
        'about_label_website': "ウェブサイト",
        'about_line': "  - {label}\t: {value}",
        'remove_selected': "選択項目を削除",
        'remove_all': "すべての項目を削除",
        'alert_files_exist': "[通知] 選択したファイルは既にリストに存在します。",
        'log_files_added': "{count}個の新しいファイルが追加されました。",
        'log_total_files': "総ファイル数: {total}個",
        'log_files_removed': "{count}個のファイルがリストから削除されました。",
        'log_all_files_removed': "ファイルリスト全体が削除されました。({count}個)",
        'log_conversion_cancelled': "ユーザーによって変換作業が中止されました。",
        'error_no_files': "[エラー] 変換するファイルを追加してください。",
        'error_no_output_video': "[エラー] ビデオを保存するパスを指定してください。",
        'error_no_output_audio': "[エラー] オーディオを保存するパスを指定してください。",
        'status_idle': "状態: 待機中",
        'status_starting': "処理開始... (総 {total}個)",
        'status_processing': "処理中: {current} / {total}",
        'status_complete': "完了: {current} / {total}",
        'status_cancelled': "中止: {current} / {total}",
        'env_check_header': "--- プログラム環境チェック ---",
        'env_success': "  [成功] {tool_name} を発見",
        'env_path': "    > パス: {path}",
        'env_error': "  [エラー] {tool_name} が見つかりません",
        'env_error_desc_video': "    > ビデオ変換タブが正常に動作しない可能性があります。",
        'env_error_desc_audio': "    > オーディオ変換タブが正常に動作しない可能性があります。",
        'env_error_desc_ffmpeg_auto_download': "    > ビデオ変換開始時にFFmpegを自動的にダウンロードします。",
        'env_check_footer': "--------------------------",
        'max_worker_log': "[システム] システム負荷を考慮し、最大{count}個のファイルを同時に変換します。",
        'conv_log_source': "  [元ファイル]\n    {path}",
        'conv_log_result_header': "\n  [結果]",
        'conv_log_skipped': "    変換済みのファイルです。（スキップ）",
        'conv_log_success': "    変換成功: {path}",
        'conv_log_error_no_file': "    [エラー] 変換は成功しましたが、出力ファイルが見つかりません。",
        'conv_log_error_fail': "    [エラー] 変換失敗 - {filename}",
        'conv_log_error_exception': "    [エラー] 致命的な例外が発生 - {error}",
        'conv_log_details_header': "\n  [詳細ログ]",
        'conv_log_details_error_header': "\n  [エラー詳細]",
        'conv_log_worker_exception': "  [エラー] ワーカー実行中に例外が発生: {filename} - {error}",
        'conv_start_video': "\n--- ビデオ変換を開始します ---",
        'conv_start_audio': "\n--- オーディオ変換を開始します ---",
        'conv_video_skip_notice': "[通知] 既存のファイルは常にスキップされます。",
        'conv_audio_overwrite_notice': "[オプション] 既存のファイルを上書きします。",
        'conv_audio_skip_notice': "[オプション] 既存のファイルをスキップします。",
        'conv_error_usmtoolkit_not_found': "\n[エラー] UsmToolkit.exe が見つかりません。変換を中止します。\n",
        'conv_error_vgmstream_not_found': "\n[エラー] vgmstream実行可能ファイル(test.exe)が見つかりません。変換を中止します。\n",
        'conv_complete_video': "\n--- ビデオ変換が完了しました ---",
        'conv_summary_video': "合計{total}ファイル中、{success}個変換、{skipped}個スキップ、{error}個エラー。\n",
        'conv_complete_audio': "\n--- オーディオ変換が完了しました ---",
        'conv_summary_audio': "合計{tracks}個のトラックがWAVファイルに変換されました。\n",
        'conv_audio_stream_error': "    [エラー] ファイルのストリーム情報を読み取れませんでした。",
        'conv_audio_stream_skipped': "    通知: 変換済みのファイル（スキップ） - {filename}",
        'conv_audio_stream_success': "    成功: {path}",
        'conv_audio_stream_fail': "    [エラー] ストリーム#{index}の変換に失敗 - {name}",
        'ffmpeg_preparing': "FFmpegを準備中... (必要に応じてダウンロード)",
        'ffmpeg_not_found': "[通知] FFmpeg (ffmpeg.exe) が見つかりません。{path} へダウンロードとインストールを試みます。",
        'ffmpeg_already_exists': "[通知] FFmpeg (ffmpeg.exe) は {path} に既に存在します。(スキップ)",
        'ffmpeg_download_start': "  > FFmpegダウンロード開始: {url}",
        'ffmpeg_download_complete': "  > FFmpegダウンロード完了。",
        'ffmpeg_download_fail': "[エラー] FFmpegダウンロード失敗: {error}",
        'ffmpeg_extract_start': "  > FFmpeg展開開始...",
        'ffmpeg_extract_complete': "  > FFmpeg展開とインストール完了: {path}",
        'ffmpeg_extract_fail': "[エラー] FFmpeg展開とインストール失敗: {error}",
        'ffmpeg_prepare_fail': "[エラー] FFmpegの準備ができていないため、ビデオ変換を開始できません。",
        'ffmpeg_no_usm_path': "[エラー] UsmToolkit.exeのパスが不明なため、FFmpegのダウンロード先を決定できません。変換を中止します。",
        'ffmpeg_zip_structure_error': "FFmpegのZIPファイル内に予期されるフォルダ構造が見つかりません。",
        'ffmpeg_exe_not_found_in_zip': "展開後、'{path}'が見つかりませんでした。ZIPファイルの構造を確認してください。",
    }
}

# --- 핵심 변환 로직 ---
class ConversionLogic:
    cpu_threads = os.cpu_count() or 1
    MAX_WORKERS = max(1, cpu_threads // 2)

    def __init__(self, log_queue, base_path):
        self.log_queue = log_queue
        self.base_path = base_path
        self._log_entry('video', 'max_worker_log', count=self.MAX_WORKERS)
        self._log_entry('audio', 'max_worker_log', count=self.MAX_WORKERS)

    def _log_entry(self, target_tab, log_key, **kwargs):
        self.log_queue.put(('log_entry', target_tab, log_key, kwargs))

    def _get_relative_path(self, full_path):
        try: return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError): return str(full_path)

    def _run_subprocess(self, command):
        return subprocess.run(
            command, capture_output=True, text=True, encoding='utf-8',
            errors='ignore', check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

    def _convert_single_video_task(self, usm_file_str, output_dir, usmtoolkit_path):
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        extract_path = Path(output_dir) / (usm_file.stem + ".mp4")
        
        log_entries = [('raw', {'text': "\n" + "-" * 60}), 
                       ('conv_log_source', {'path': self._get_relative_path(usm_file)})]
        status = "unknown"

        if extract_path.exists():
            log_entries.append(('conv_log_result_header', {}))
            log_entries.append(('conv_log_skipped', {}))
            status = "skipped"
        else:
            command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(Path(output_dir).resolve())]
            try:
                result = subprocess.run(command, cwd=usmtoolkit_dir, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                log_entries.append(('conv_log_result_header', {}))
                if extract_path.exists():
                    log_entries.append(('conv_log_success', {'path': self._get_relative_path(extract_path)}))
                    status = "success"
                else:
                    log_entries.append(('conv_log_error_no_file', {}))
                    status = "error"
                tool_output = result.stdout.strip()
                if tool_output:
                    log_entries.append(('conv_log_details_header', {}))
                    log_entries.extend([('raw', {'text': f"    > {line}"}) for line in tool_output.splitlines()])
            except subprocess.CalledProcessError as e:
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_fail', {'filename': usm_file.name}))
                status = "error"
                error_output = (e.stderr or e.stdout or "No error output.").strip()
                if error_output:
                    log_entries.append(('conv_log_details_error_header', {}))
                    log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])
            except Exception as e:
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_exception', {'error': e}))
                status = "error"
        log_entries.append(('raw', {'text': "-" * 60}))
        return status, log_entries

    def run_video_conversion(self, input_paths, output_dir, usmtoolkit_path, cancel_event):
        target_tab = 'video'
        self._log_entry(target_tab, 'conv_start_video')
        self._log_entry(target_tab, 'conv_video_skip_notice')
        if not usmtoolkit_path:
            self._log_entry(target_tab, 'conv_error_usmtoolkit_not_found')
            self.log_queue.put(('__VIDEO_DONE__', True))
            return

        total_files = len(input_paths)
        success_count, skipped_count, error_count, completed_tasks = 0, 0, 0, 0
        self.log_queue.put(('progress_start', target_tab, total_files))

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_single_video_task, path, output_dir, usmtoolkit_path): path for path in input_paths}
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_event.is_set(): break
                try:
                    status, log_entries = future.result()
                    for key, kwargs in log_entries: self._log_entry(target_tab, key, **kwargs)
                    if status == "success": success_count += 1
                    elif status == "skipped": skipped_count += 1
                    else: error_count += 1
                except Exception as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                    error_count += 1
                finally:
                    completed_tasks += 1
                    self.log_queue.put(('progress_update', target_tab, completed_tasks))
        
        if cancel_event.is_set(): self._log_entry(target_tab, 'log_conversion_cancelled')
        self._log_entry(target_tab, 'conv_complete_video')
        self._log_entry(target_tab, 'conv_summary_video', total=total_files, success=success_count, skipped=skipped_count, error=error_count)
        self.log_queue.put(('__VIDEO_DONE__', cancel_event.is_set()))

    def run_audio_conversion(self, input_paths, output_dir, vgmstream_path, overwrite, cancel_event):
        target_tab = 'audio'
        self._log_entry(target_tab, 'conv_start_audio')
        self._log_entry(target_tab, 'conv_audio_overwrite_notice' if overwrite else 'conv_audio_skip_notice')

        if not vgmstream_path:
            self._log_entry(target_tab, 'conv_error_vgmstream_not_found')
            self.log_queue.put(('__AUDIO_DONE__', True))
            return
            
        total_files = len(input_paths)
        total_converted_tracks = 0
        completed_tasks = 0
        self.log_queue.put(('progress_start', target_tab, total_files))

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_audio_container, path, output_dir, vgmstream_path, overwrite, cancel_event): path for path in input_paths}
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_event.is_set(): break
                try:
                    converted_count, log_entries = future.result()
                    for key, kwargs in log_entries: self._log_entry(target_tab, key, **kwargs)
                    total_converted_tracks += converted_count
                except Exception as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                finally:
                    completed_tasks += 1
                    self.log_queue.put(('progress_update', target_tab, completed_tasks))
                    
        if cancel_event.is_set(): self._log_entry(target_tab, 'log_conversion_cancelled')
        self._log_entry(target_tab, 'conv_complete_audio')
        self._log_entry(target_tab, 'conv_summary_audio', tracks=total_converted_tracks)
        self.log_queue.put(('__AUDIO_DONE__', cancel_event.is_set()))

    def _get_stream_count(self, file_path, vgmstream_path):
        result = self._run_subprocess([str(vgmstream_path), "-m", str(file_path)])
        if result.returncode != 0: return 0
        for line in result.stdout.splitlines():
            if line.startswith("stream count:"):
                try: return int(line.split(":")[1].strip())
                except (ValueError, IndexError): return 1
        return 1

    def _get_stream_name(self, file_path, stream_num, vgmstream_path):
        result = self._run_subprocess([str(vgmstream_path), "-m", "-s", str(stream_num), str(file_path)])
        if result.returncode != 0: return f"track_{stream_num}"
        for line in result.stdout.splitlines():
            if line.startswith("stream name:"):
                return line.split(":")[1].strip().split(';')[0].strip()
        return f"track_{stream_num}"

    def _convert_audio_container(self, item_path_str, output_dir, vgmstream_path, overwrite, cancel_event):
        item_path = Path(item_path_str)
        log_entries = [('raw', {'text': "\n" + "-" * 60}),
                       ('conv_log_source', {'path': self._get_relative_path(item_path)}),
                       ('conv_log_result_header', {})]
        total_converted = 0
        
        item_output_folder = Path(output_dir) / item_path.stem
        item_output_folder.mkdir(parents=True, exist_ok=True)

        num_streams = self._get_stream_count(item_path, vgmstream_path)
        if num_streams == 0:
            log_entries.append(('conv_audio_stream_error', {}))
            log_entries.append(('raw', {'text': "-" * 60}))
            return 0, log_entries

        for i in range(1, num_streams + 1):
            if cancel_event.is_set(): break
            
            stream_name = self._get_stream_name(item_path, i, vgmstream_path)
            output_file = item_output_folder / f"{stream_name}.wav"

            if not overwrite and output_file.exists():
                log_entries.append(('conv_audio_stream_skipped', {'filename': output_file.name}))
                continue

            command = [str(vgmstream_path), "-s", str(i), "-o", str(output_file), str(item_path)]
            result = self._run_subprocess(command)

            if result.returncode == 0 and output_file.exists():
                log_entries.append(('conv_audio_stream_success', {'path': self._get_relative_path(output_file)}))
                total_converted += 1
            else:
                log_entries.append(('conv_audio_stream_fail', {'index': i, 'name': stream_name}))
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    log_entries.append(('conv_log_details_error_header', {}))
                    log_entries.extend([('raw', {'text': f"      > {line}"}) for line in error_output.splitlines()])

        if cancel_event.is_set(): log_entries.append(('log_conversion_cancelled', {}))
        log_entries.append(('raw', {'text': "-" * 60}))
        return total_converted, log_entries

# --- FFmpeg 다운로드 및 설치 클래스 (단순화 버전) ---
class FFmpegDownloader:
    FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    FFMPEG_ZIP_FILENAME = "ffmpeg_temp.zip"
    FFMPEG_EXE_NAME = "ffmpeg.exe"

    def __init__(self, log_queue, usmtoolkit_path_parent_dir: Path, get_lang_data_func):
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_path_parent_dir
        self.ffmpeg_path = self.download_dir / self.FFMPEG_EXE_NAME
        self.get_lang_data = get_lang_data_func
        os.makedirs(self.download_dir, exist_ok=True)

    def _log_entry(self, log_key, **kwargs):
        self.log_queue.put(('log_entry', 'video', log_key, kwargs))

    def ensure_ffmpeg_ready(self) -> concurrent.futures.Future:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._actual_download_and_extract)
        executor.shutdown(wait=False)
        return future

    def _actual_download_and_extract(self) -> bool:
        local_zip_path = self.download_dir / self.FFMPEG_ZIP_FILENAME
        temp_extract_dir = None
        
        if self.ffmpeg_path.exists():
            self._log_entry('ffmpeg_already_exists', path=self.download_dir)
            return True

        self._log_entry('ffmpeg_not_found', path=self.download_dir)
        try:
            self._log_entry('ffmpeg_download_start', url=self.FFMPEG_URL)
            with urllib.request.urlopen(self.FFMPEG_URL) as response, open(local_zip_path, 'wb') as out_file:
                if response.status != 200:
                    raise Exception(f"HTTP Error: {response.status} {response.reason}")
                shutil.copyfileobj(response, out_file)
            
            self._log_entry('ffmpeg_download_complete')

            self._log_entry('ffmpeg_extract_start')
            temp_extract_dir = self.download_dir / "ffmpeg_extracted_temp"
            os.makedirs(temp_extract_dir, exist_ok=True)
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                ffmpeg_internal_path = None
                for name in zip_ref.namelist():
                    if name.endswith(f'/bin/{self.FFMPEG_EXE_NAME}'):
                        ffmpeg_internal_path = name
                        break
                if not ffmpeg_internal_path:
                    d = self.get_lang_data()
                    raise Exception(d['ffmpeg_zip_structure_error'])
                zip_ref.extract(ffmpeg_internal_path, temp_extract_dir)
                extracted_exe_full_path = temp_extract_dir / ffmpeg_internal_path
                shutil.move(extracted_exe_full_path, self.ffmpeg_path)
            self._log_entry('ffmpeg_extract_complete', path=self.ffmpeg_path)
            return True
        except Exception as e:
            self._log_entry('ffmpeg_download_fail', error=e)
            return False
        finally:
            if local_zip_path.exists():
                os.remove(local_zip_path)
            if temp_extract_dir and temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir)

# --- GUI 애플리케이션 ---
class App(tk.Tk):
    ABOUT_INFO = {
        'program': "Audio Video Converter",
        'version': "2.2.0",
        'updated': "2025-07-15",
        'license': "MIT License",
        'developer': "(Github) IZH318",
        'website': "https://github.com/IZH318",
    }

    def __init__(self):
        super().__init__()
        
        self.lang_data = LANGUAGES['ko']
        self.usmtoolkit_path, self.vgmstream_path = None, None
        
        self.video_full_paths, self.audio_full_paths = [], []
        self.video_filenames_var, self.audio_filenames_var = tk.StringVar(), tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)

        self.video_cancel_event, self.audio_cancel_event = threading.Event(), threading.Event()
        self.video_total_files, self.audio_total_files = 0, 0
        
        self.video_log_history = []
        self.audio_log_history = []

        self.base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        self.log_queue = queue.Queue()
        self.logic = ConversionLogic(self.log_queue, self.base_path)

        self._configure_window()
        self._find_tools()
        
        ffmpeg_parent_dir = self.usmtoolkit_path.parent if self.usmtoolkit_path else self.base_path
        self.ffmpeg_downloader = FFmpegDownloader(self.log_queue, ffmpeg_parent_dir, lambda: self.lang_data)

        self._setup_ui()
        self._log_initial_status()
        self._process_log_queue()

    def _configure_window(self):
        self.title(self.lang_data['window_title'])
        width, height = 800, 600
        self.geometry(f'{width}x{height}+{self.winfo_screenwidth()//2 - width//2}+{self.winfo_screenheight()//2 - height//2}')

    def _find_tools(self):
        for root, _, files in os.walk(self.base_path):
            if not self.usmtoolkit_path and "usmtoolkit.exe" in (f.lower() for f in files):
                self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "test.exe" in (f.lower() for f in files) and "vgmstream" in str(Path(root)).lower():
                self.vgmstream_path = Path(root) / "test.exe"

    def _setup_ui(self):
        self._create_main_menu()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.video_tab = ttk.Frame(self.notebook)
        self.audio_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.video_tab, text=self.lang_data['video_tab'])
        self.notebook.add(self.audio_tab, text=self.lang_data['audio_tab'])
        self.video_widgets, self.video_log_text, self.video_ui_elements = self._build_conversion_tab_ui(self.video_tab, 'video')
        self.audio_widgets, self.audio_log_text, self.audio_ui_elements = self._build_conversion_tab_ui(self.audio_tab, 'audio')

    def _create_main_menu(self):
        self.menubar = Menu(self)
        self.config(menu=self.menubar)
        d = self.lang_data
        self.info_menu_label = d['menu_info']
        self.menubar.add_command(label=self.info_menu_label, command=self._show_about_info)
        self.lang_menu_label = d['menu_language']
        self.lang_menu = Menu(self.menubar, tearoff=0)
        self.lang_menu.add_command(label="한국어", command=lambda: self.switch_language('ko'))
        self.lang_menu.add_command(label="English", command=lambda: self.switch_language('en'))
        self.lang_menu.add_command(label="日本語", command=lambda: self.switch_language('ja'))
        self.menubar.add_cascade(label=self.lang_menu_label, menu=self.lang_menu)

    def switch_language(self, lang_code):
        if lang_code in LANGUAGES:
            self.lang_data = LANGUAGES[lang_code]
            self._update_ui_text()
            self._redraw_logs()

    def _update_ui_text(self):
        d = self.lang_data
        self.title(d['window_title'])
        self.menubar.entryconfig(self.info_menu_label, label=d['menu_info'])
        self.menubar.entryconfig(self.lang_menu_label, label=d['menu_language'])
        self.info_menu_label = d['menu_info']
        self.lang_menu_label = d['menu_language']
        self.notebook.tab(self.video_tab, text=d['video_tab'])
        self.notebook.tab(self.audio_tab, text=d['audio_tab'])
        
        is_video_converting = self.video_widgets['action_btn']['text'] == d['cancel_conversion']
        self.video_ui_elements['log_frame_container'].config(text=d['log_section'])
        self.video_ui_elements['input_frame'].config(text=d['input_section'])
        self.video_widgets['add_files_btn'].config(text=d['add_files'])
        self.video_widgets['add_folder_btn'].config(text=d['add_folder'])
        self.video_ui_elements['list_container'].config(text=d['file_list_section'])
        self.video_ui_elements['output_frame'].config(text=d['output_section'])
        self.video_ui_elements['browse_btn'].config(text=d['browse'])
        self.video_ui_elements['action_frame'].config(text=d['action_section'])
        self.video_widgets['action_btn'].config(text=d['cancel_conversion'] if is_video_converting else d['start_conversion'])
        if not is_video_converting:
            self.video_widgets['status_label'].config(text=d['status_idle'])

        is_audio_converting = self.audio_widgets['action_btn']['text'] == d['cancel_conversion']
        self.audio_ui_elements['log_frame_container'].config(text=d['log_section'])
        self.audio_ui_elements['input_frame'].config(text=d['input_section'])
        self.audio_widgets['add_files_btn'].config(text=d['add_files'])
        self.audio_widgets['add_folder_btn'].config(text=d['add_folder'])
        self.audio_ui_elements['list_container'].config(text=d['file_list_section'])
        self.audio_ui_elements['output_frame'].config(text=d['output_section'])
        self.audio_ui_elements['browse_btn'].config(text=d['browse'])
        self.audio_ui_elements['action_frame'].config(text=d['action_section'])
        self.audio_widgets['action_btn'].config(text=d['cancel_conversion'] if is_audio_converting else d['start_conversion'])
        self.audio_widgets['overwrite_check'].config(text=d['overwrite_option'])
        if not is_audio_converting:
            self.audio_widgets['status_label'].config(text=d['status_idle'])
        
    def _show_about_info(self):
        try:
            target_tab = 'video' if self.notebook.select() == str(self.video_tab) else 'audio'
        except tk.TclError:
            target_tab = 'video'
        
        self._add_log_entry(target_tab, 'raw', text="\n" + "-" * 70)
        self._add_log_entry(target_tab, 'about_header')
        self._add_log_entry(target_tab, 'raw', text="")
        
        for key, value in self.ABOUT_INFO.items():
            label_key = f'about_label_{key}'
            self._add_log_entry(target_tab, 'about_line_key', label_key=label_key, value=value)

        self._add_log_entry(target_tab, 'raw', text="-" * 70 + "\n")

    def _build_conversion_tab_ui(self, parent_tab, tab_type):
        d = self.lang_data
        is_audio_tab = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio_tab else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio_tab else self.video_full_paths
        filenames_var = self.audio_filenames_var if is_audio_tab else self.video_filenames_var

        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(fill=tk.BOTH, expand=True)
        controls_frame = ttk.Frame(tab_pane, width=240)
        tab_pane.add(controls_frame) 
        log_frame_container = ttk.LabelFrame(tab_pane, text=d['log_section'])
        tab_pane.add(log_frame_container)
        
        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state='disabled')
        log_text_widget.pack(side='top', fill="both", expand=True, padx=5, pady=(5,0))
        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=(2,5))
        status_label = ttk.Label(status_frame, text=d['status_idle'])
        status_label.pack(side='left')
        progress_bar = ttk.Progressbar(status_frame, orient='horizontal', mode='determinate')
        progress_bar.pack(side='left', fill='x', expand=True, padx=(5,0))

        input_frame = ttk.LabelFrame(controls_frame, text=d['input_section'])
        input_frame.pack(fill='x', pady=5, padx=5)
        add_files_btn = ttk.Button(input_frame, text=d['add_files'], command=lambda: self._add_files(file_types, full_paths, filenames_var, tab_type))
        add_files_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        add_folder_btn = ttk.Button(input_frame, text=d['add_folder'], command=lambda: self._add_folder(file_types, full_paths, filenames_var, tab_type))
        add_folder_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')

        list_container = ttk.LabelFrame(controls_frame, text=d['file_list_section'])
        list_container.pack(fill='both', expand=True, pady=5, padx=5)
        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
        scrollbar.pack(side='right', fill='y')
        listbox.config(yscrollcommand=scrollbar.set)
        self._create_right_click_menu(listbox, full_paths, filenames_var, tab_type)
        
        output_frame = ttk.LabelFrame(controls_frame, text=d['output_section'])
        output_frame.pack(fill='x', pady=5, padx=5)
        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        browse_btn = ttk.Button(output_frame, text=d['browse'], command=lambda: self._select_output_folder(output_entry))
        browse_btn.pack(side='left', padx=5, pady=5)

        action_frame = ttk.LabelFrame(controls_frame, text=d['action_section'])
        action_frame.pack(fill='x', pady=5, padx=5)
        action_button = ttk.Button(action_frame, text=d['start_conversion'])
        
        widgets_dict = {'action_btn': action_button, 'add_files_btn': add_files_btn, 'add_folder_btn': add_folder_btn, 'output_entry': output_entry, 'progress': progress_bar, 'status_label': status_label}
        ui_elements_for_lang_update = {'log_frame_container': log_frame_container, 'input_frame': input_frame, 'list_container': list_container, 'output_frame': output_frame, 'action_frame': action_frame, 'browse_btn': browse_btn}
        
        if is_audio_tab:
            action_button.pack(side='left', pady=5, padx=5)
            overwrite_check = ttk.Checkbutton(action_frame, text=d['overwrite_option'], variable=self.audio_overwrite_var)
            overwrite_check.pack(side='left', pady=5, padx=10)
            action_button.config(command=lambda: self.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get()))
            widgets_dict['overwrite_check'] = overwrite_check
        else:
            action_button.pack(fill='x', pady=5, padx=5)
            action_button.config(command=lambda: self.start_video_conversion(output_entry.get()))

        return widgets_dict, log_text_widget, ui_elements_for_lang_update
    
    def _log_initial_status(self):
        self.video_log_history.clear()
        self.audio_log_history.clear()

        self._add_log_entry('video', 'env_check_header')
        if self.usmtoolkit_path:
            self._add_log_entry('video', 'env_success', tool_name="UsmToolkit.exe")
            self._add_log_entry('video', 'env_path', path=self.logic._get_relative_path(self.usmtoolkit_path))
            if self.ffmpeg_downloader.ffmpeg_path.exists():
                self._add_log_entry('video', 'env_success', tool_name="FFmpeg (ffmpeg.exe)")
                self._add_log_entry('video', 'env_path', path=self.logic._get_relative_path(self.ffmpeg_downloader.ffmpeg_path))
            else:
                self._add_log_entry('video', 'env_error', tool_name="FFmpeg (ffmpeg.exe)")
                self._add_log_entry('video', 'env_error_desc_ffmpeg_auto_download')
        else:
            self._add_log_entry('video', 'env_error', tool_name="UsmToolkit.exe")
            self._add_log_entry('video', 'env_error_desc_video')
            self._add_log_entry('video', 'env_error', tool_name="FFmpeg (ffmpeg.exe)")
            self._add_log_entry('video', 'env_error_desc_ffmpeg_auto_download')
        self._add_log_entry('video', 'env_check_footer')
        self._add_log_entry('video', 'raw', text='\n')

        self._add_log_entry('audio', 'env_check_header')
        if self.vgmstream_path:
            self._add_log_entry('audio', 'env_success', tool_name="vgmstream(test.exe)")
            self._add_log_entry('audio', 'env_path', path=self.logic._get_relative_path(self.vgmstream_path))
        else:
            self._add_log_entry('audio', 'env_error', tool_name="vgmstream(test.exe)")
            self._add_log_entry('audio', 'env_error_desc_audio')
        self._add_log_entry('audio', 'env_check_footer')
        self._add_log_entry('audio', 'raw', text='\n')

    def _create_right_click_menu(self, listbox, full_paths, filenames_var, tab_type):
        menu = Menu(listbox, tearoff=0)
        menu.add_command(label="", command=lambda: self._remove_selected_from_list(listbox, full_paths, filenames_var, tab_type))
        menu.add_command(label="", command=lambda: self._clear_list(full_paths, filenames_var, tab_type))
        def show_menu(event):
            d = self.lang_data
            menu.entryconfig(0, label=d['remove_selected'], state="normal" if listbox.curselection() else "disabled")
            menu.entryconfig(1, label=d['remove_all'], state="normal" if listbox.size() > 0 else "disabled")
            menu.post(event.x_root, event.y_root)
        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self._remove_selected_from_list(listbox, full_paths, filenames_var, tab_type))

    def _set_ui_state(self, widgets, state):
        for widget_name, widget in widgets.items():
            if widget_name in ['progress', 'status_label']: continue
            if isinstance(widget, ttk.Entry) and state == 'disabled': widget.config(state='readonly')
            else: widget.config(state=state)

    def _reset_video_ui_state(self):
        d = self.lang_data
        self.video_cancel_event.clear()
        self._set_ui_state(self.video_widgets, 'normal')
        self.video_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_video_conversion(self.video_widgets['output_entry'].get()))
        self.video_widgets['status_label'].config(text=d['status_idle'])
        self.video_widgets['progress']['value'] = 0

    def _reset_audio_ui_state(self):
        d = self.lang_data
        self.audio_cancel_event.clear()
        self._set_ui_state(self.audio_widgets, 'normal')
        self.audio_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_audio_conversion(self.audio_widgets['output_entry'].get(), self.audio_overwrite_var.get()))
        self.audio_widgets['status_label'].config(text=d['status_idle'])
        self.audio_widgets['progress']['value'] = 0

    def _select_files(self, ft): return list(filedialog.askopenfilenames(title="파일을 선택하세요", filetypes=ft) or [])
    def _select_folder_and_search(self, ft):
        folder = filedialog.askdirectory(title="폴더를 선택하세요")
        if not folder: return []
        exts = [ext.strip('*.') for _, p in ft for ext in p.split()]
        return [str(Path(r) / f) for r, _, fs in os.walk(folder) for f in fs if any(f.lower().endswith(f".{ext}") for ext in exts)]
    
    def _select_output_folder(self, entry_widget):
        folder = filedialog.askdirectory(title="저장할 폴더를 선택하세요")
        if folder:
            entry_widget.config(state='normal'); entry_widget.delete(0, tk.END); entry_widget.insert(0, folder); entry_widget.config(state='readonly')

    def _update_listbox(self, fp, fv): fv.set([os.path.basename(p) for p in fp])
    def _add_paths_to_list(self, new_paths, full_paths, tab_type, filenames_var):
        if not new_paths: return
        unique_new_paths = [p for p in new_paths if p not in set(full_paths)]
        if not unique_new_paths:
            self._add_log_entry(tab_type, 'raw', text='\n')
            self._add_log_entry(tab_type, 'alert_files_exist')
            self._add_log_entry(tab_type, 'raw', text='\n')
            return
        full_paths.extend(unique_new_paths)
        self._update_listbox(full_paths, filenames_var)
        self._add_log_entry(tab_type, 'raw', text='\n')
        self._add_log_entry(tab_type, 'log_files_added', count=len(unique_new_paths))
        self._add_log_entry(tab_type, 'log_total_files', total=len(full_paths))
        self._add_log_entry(tab_type, 'raw', text='\n')
        
    def _add_files(self, ft, fp, fv, tt): self._add_paths_to_list(self._select_files(ft), fp, tt, fv)
    def _add_folder(self, ft, fp, fv, tt): self._add_paths_to_list(self._select_folder_and_search(ft), fp, tt, fv)
        
    def _remove_selected_from_list(self, lb, fp, fv, tt):
        sel_idx = lb.curselection()
        if not sel_idx: return
        for i in sorted(sel_idx, reverse=True): del fp[i]
        self._update_listbox(fp, fv)
        self._add_log_entry(tt, 'raw', text='\n')
        self._add_log_entry(tt, 'log_files_removed', count=len(sel_idx))
        self._add_log_entry(tt, 'raw', text='\n')
        
    def _clear_list(self, fp, fv, tt):
        if not fp: return
        count = len(fp)
        fp.clear()
        self._update_listbox(fp, fv)
        self._add_log_entry(tt, 'raw', text='\n')
        self._add_log_entry(tt, 'log_all_files_removed', count=count)
        self._add_log_entry(tt, 'raw', text='\n')

    def start_video_conversion(self, output_dir):
        if not self.video_full_paths: self._add_log_entry('video', 'error_no_files'); return
        if not output_dir: self._add_log_entry('video', 'error_no_output_video'); return
        self._start_ffmpeg_preparation(output_dir)

    def _start_ffmpeg_preparation(self, output_dir):
        if not self.usmtoolkit_path:
            self._add_log_entry('video', 'ffmpeg_no_usm_path')
            return

        self._set_ui_state(self.video_widgets, 'disabled')
        self._add_log_entry('video', 'raw', text="\n")
        self._add_log_entry('video', 'ffmpeg_preparing')
        
        download_future = self.ffmpeg_downloader.ensure_ffmpeg_ready()

        def check_ffmpeg_status():
            if download_future.done():
                try:
                    is_ready = download_future.result()
                    if is_ready:
                        self._start_actual_video_conversion(output_dir)
                    else:
                        self._add_log_entry('video', 'ffmpeg_prepare_fail')
                        self._reset_video_ui_state()
                except Exception as e:
                    self._add_log_entry('video', 'ffmpeg_prepare_fail')
                    self._add_log_entry('video', 'conv_log_error_exception', error=e)
                    self._reset_video_ui_state()
            else:
                self.after(100, check_ffmpeg_status)

        self.after(100, check_ffmpeg_status)

    def _start_actual_video_conversion(self, output_dir):
        d = self.lang_data
        self.video_cancel_event.clear()

        threading.Thread(
            target=self.logic.run_video_conversion,
            daemon=True,
            args=(self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.video_cancel_event)
        ).start()

        self.video_widgets['action_btn'].config(
            text=d['cancel_conversion'],
            command=self.cancel_video_conversion,
            state='normal'
        )

    def cancel_video_conversion(self): 
        self.video_widgets['action_btn'].config(state='disabled')
        self.video_cancel_event.set()

    def start_audio_conversion(self, output_dir, overwrite):
        if not self.audio_full_paths: self._add_log_entry('audio', 'error_no_files'); return
        if not output_dir: self._add_log_entry('audio', 'error_no_output_audio'); return

        self.audio_cancel_event.clear()
        self._set_ui_state(self.audio_widgets, 'disabled')
        self.audio_widgets['action_btn'].config(text=self.lang_data['cancel_conversion'], command=self.cancel_audio_conversion, state='normal')
        threading.Thread(target=self.logic.run_audio_conversion, daemon=True, args=(self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.audio_cancel_event)).start()

    def cancel_audio_conversion(self): 
        self.audio_widgets['action_btn'].config(state='disabled')
        self.audio_cancel_event.set()

    def _render_log_entry(self, key, kwargs):
        if key == 'raw': return kwargs.get('text', '')
        
        if key == 'about_line_key':
            label_key = kwargs.get('label_key')
            label = self.lang_data.get(label_key, label_key)
            value = kwargs.get('value', '')
            return self.lang_data.get('about_line', "{label}: {value}").format(label=label, value=value)

        template = self.lang_data.get(key, f"<{key} not found>")
        try:
            return template.format(**kwargs)
        except (KeyError, TypeError) as e:
            return f"<{key}: formatting error {e}>"

    def _add_log_entry(self, target_tab, log_key, **kwargs):
        history = self.video_log_history if target_tab == 'video' else self.audio_log_history
        log_widget = self.video_log_text if target_tab == 'video' else self.audio_log_text
        history.append((log_key, kwargs))
        message = self._render_log_entry(log_key, kwargs)
        self.log_to_gui(message + '\n', log_widget)

    def _redraw_logs(self):
        log_widget = self.video_log_text
        history = self.video_log_history
        log_widget.config(state='normal')
        log_widget.delete('1.0', tk.END)
        for key, kwargs in history:
            message = self._render_log_entry(key, kwargs)
            log_widget.insert(tk.END, message + '\n')
        log_widget.config(state='disabled')
        log_widget.see(tk.END)

        log_widget = self.audio_log_text
        history = self.audio_log_history
        log_widget.config(state='normal')
        log_widget.delete('1.0', tk.END)
        for key, kwargs in history:
            message = self._render_log_entry(key, kwargs)
            log_widget.insert(tk.END, message + '\n')
        log_widget.config(state='disabled')
        log_widget.see(tk.END)

    def log_to_gui(self, message, log_widget):
        log_widget.config(state='normal')
        log_widget.insert(tk.END, message)
        log_widget.config(state='disabled')
        log_widget.see(tk.END)

    def _process_log_queue(self):
        MAX_MESSAGES_PER_CYCLE = 200
        try:
            for _ in range(MAX_MESSAGES_PER_CYCLE):
                msg = self.log_queue.get_nowait()
                msg_type, *args = msg
                d = self.lang_data

                if msg_type.startswith('__'): 
                    was_cancelled = args[0]
                    if msg_type == '__VIDEO_DONE__':
                        widgets, total = self.video_widgets, self.video_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_video_ui_state()
                    elif msg_type == '__AUDIO_DONE__':
                        widgets, total = self.audio_widgets, self.audio_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_audio_ui_state()
                
                elif msg_type == 'log_entry':
                    target_tab, log_key, kwargs = args
                    history = self.video_log_history if target_tab == 'video' else self.audio_log_history
                    history.append((log_key, kwargs))
                    self._redraw_logs()

                elif msg_type == 'progress_start':
                    target_tab, total = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    if target_tab == 'video': self.video_total_files = total
                    else: self.audio_total_files = total
                    widgets['progress'].config(maximum=total, value=0)
                    widgets['status_label'].config(text=d['status_starting'].format(total=total))
                
                elif msg_type == 'progress_update':
                    target_tab, value = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    total = self.video_total_files if target_tab == 'video' else self.audio_total_files
                    widgets['progress']['value'] = value
                    widgets['status_label'].config(text=d['status_processing'].format(current=value, total=total))

        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()