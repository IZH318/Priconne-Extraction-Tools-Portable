"""
Controller/View 계층 테스트 모듈.

CancellationToken, get_lang_dict(), 상태 플래그, SQL 방어,
Constants 불변성, 그리고 languages.py 에러 핸들링을 검증합니다.
"""
from __future__ import annotations
import os

import pytest
from src.cancellation_token import CancellationToken
from src.story_viewer.db_helper import _validate_identifier


# ===== CancellationToken Tests =====

class TestCancellationToken:
    """CancellationToken의 cancel/reset/is_cancelled 동작 검증."""

    def test_initial_state_is_not_cancelled(self):
        token = CancellationToken()
        assert token.is_cancelled is False

    def test_cancel_sets_cancelled(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled is True

    def test_reset_clears_cancelled(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled is True
        token.reset()
        assert token.is_cancelled is False

    def test_throw_if_cancelled_raises(self):
        """throw_if_cancelled()가 취소 시 InterruptedError를 발생시키는지 확인합니다."""
        token = CancellationToken()
        # 취소 전에는 예외 없음
        token.throw_if_cancelled()  # 예외 발생하지 않아야 함
        # 취소 후에는 예외 발생
        token.cancel()
        with pytest.raises(InterruptedError, match="cancelled"):
            token.throw_if_cancelled()

    def test_multiple_cancel_reset_cycles(self):
        """여러 번의 cancel/reset 사이클이 올바르게 동작하는지 확인합니다."""
        token = CancellationToken()
        for _ in range(5):
            assert token.is_cancelled is False
            token.cancel()
            assert token.is_cancelled is True
            token.reset()
        assert token.is_cancelled is False


# ===== Language Key Consistency Tests =====

class TestLanguageKeyConsistency:
    """languages.json 내 모듈별 언어 키가 모든 언어에 일관성 있게 정의되어 있는지 검증."""

    def test_all_modules_have_consistent_keys(self):
        import json
        json_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'languages.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for module_name, module_data in data.items():
            if not isinstance(module_data, dict):
                continue
            
            lang_codes = [lc for lc in module_data if isinstance(module_data[lc], dict)]
            if len(lang_codes) < 2:
                continue

            ref_keys = set(module_data[lang_codes[0]].keys())
            for lc in lang_codes[1:]:
                lc_keys = set(module_data[lc].keys())
                missing = ref_keys - lc_keys
                extra = lc_keys - ref_keys
                assert not missing, f"{module_name}.{lc} is missing keys vs {lang_codes[0]}: {missing}"
                assert not extra, f"{module_name}.{lc} has extra keys vs {lang_codes[0]}: {extra}"

    def test_resource_remover_has_title_keys(self):
        """P0/P1에서 추가된 title 키들이 모든 언어에 존재하는지 확인."""
        import json
        json_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'languages.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        required_keys = ['info_title', 'warn_title', 'error_title', 'no_files_found', 'error_delete_failed']
        for lang in ['ko', 'en', 'ja']:
            for key in required_keys:
                assert key in data['resource_remover'][lang], f"resource_remover.{lang} missing '{key}'"


# ===== Constants Immutability Tests =====

class TestConstantsImmutability:
    """constants.py의 컬렉션 타입이 불변(tuple)임을 검증."""

    def test_renamer_target_folders_is_tuple(self):
        from src.constants import RENAMER_TARGET_FOLDERS
        assert isinstance(RENAMER_TARGET_FOLDERS, tuple), "RENAMER_TARGET_FOLDERS should be tuple, not list"

    def test_av_temp_extensions_is_tuple(self):
        from src.constants import AV_TEMP_EXTENSIONS
        assert isinstance(AV_TEMP_EXTENSIONS, tuple), "AV_TEMP_EXTENSIONS should be tuple, not list"

    def test_unity_supported_extensions_is_tuple(self):
        from src.constants import UNITY_SUPPORTED_EXTENSIONS
        assert isinstance(UNITY_SUPPORTED_EXTENSIONS, tuple), "UNITY_SUPPORTED_EXTENSIONS should be tuple, not list"


# ===== SQL Identifier Validation Tests =====

class TestSQLIdentifierValidation:
    """db_helper._validate_identifier()의 화이트리스트 검증 동작."""

    def test_valid_simple_name(self):
        assert _validate_identifier("event_name") == "event_name"

    def test_valid_name_with_numbers(self):
        assert _validate_identifier("col_2") == "col_2"

    def test_rejects_semicolon_injection(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("name; DROP TABLE")

    def test_rejects_quote_injection(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier('name"--')

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("")

    def test_rejects_leading_number(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _validate_identifier("123abc")


# ===== Languages Module Tests =====

class TestLanguagesModule:
    """languages.py 모듈의 로딩 및 구조 검증."""

    def test_module_exports_all_dicts(self):
        from src.languages import (
            AV_CONVERTER_LANGUAGES, RENAMER_LANGUAGES,
            RESOURCE_REMOVER_LANGUAGES, STORY_VIEWER_LANGUAGES,
            UNITY_CONVERTER_LANGUAGES
        )
        assert isinstance(AV_CONVERTER_LANGUAGES, dict)
        assert isinstance(RENAMER_LANGUAGES, dict)
        assert isinstance(RESOURCE_REMOVER_LANGUAGES, dict)
        assert isinstance(STORY_VIEWER_LANGUAGES, dict)
        assert isinstance(UNITY_CONVERTER_LANGUAGES, dict)

    def test_all_modules_have_three_languages(self):
        from src.languages import (
            AV_CONVERTER_LANGUAGES, RENAMER_LANGUAGES,
            RESOURCE_REMOVER_LANGUAGES, STORY_VIEWER_LANGUAGES,
            UNITY_CONVERTER_LANGUAGES
        )
        for name, d in [
            ('av_converter', AV_CONVERTER_LANGUAGES),
            ('renamer', RENAMER_LANGUAGES),
            ('resource_remover', RESOURCE_REMOVER_LANGUAGES),
            ('story_viewer', STORY_VIEWER_LANGUAGES),
            ('unity_converter', UNITY_CONVERTER_LANGUAGES),
        ]:
            assert 'ko' in d, f"{name} missing 'ko'"
            assert 'en' in d, f"{name} missing 'en'"
            assert 'ja' in d, f"{name} missing 'ja'"


# ===== Controller get_lang_dict Tests =====

def test_resource_remover_controller_get_lang_dict():
    """ResourceRemoverController.get_lang_dict()가 올바른 언어 딕셔너리를 반환하는지 검증."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        from src.resource_remover.controller import ResourceRemoverController
        controller = ResourceRemoverController(root, app_lang_var=lang_var)

        d = controller.get_lang_dict()
        assert isinstance(d, dict)
        assert 'btn_start' in d

        lang_var.set('en')
        d = controller.get_lang_dict()
        assert isinstance(d, dict)
        assert 'btn_start' in d
    finally:
        root.destroy()


def test_resource_remover_is_complete_flag():
    """ResourceRemoverController.is_complete 플래그가 올바르게 관리되는지 검증."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        from src.resource_remover.controller import ResourceRemoverController
        controller = ResourceRemoverController(root, app_lang_var=lang_var)

        assert controller.is_complete is False

        lang_dict = controller.get_lang_dict()
        from unittest import mock
        with mock.patch('tkinter.messagebox.showinfo'):
            controller._handle_delete_done(5, [], "test.log", lang_dict)
        assert controller.is_complete is True

        controller.is_complete = False
        assert controller.is_complete is False
    finally:
        root.destroy()


def test_resource_remover_delete_done_with_errors():
    """에러가 있을 때 is_complete 플래그와 상태 색상이 올바르게 설정되는지 검증."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        from src.resource_remover.controller import ResourceRemoverController
        controller = ResourceRemoverController(root, app_lang_var=lang_var)

        lang_dict = controller.get_lang_dict()
        from unittest import mock
        with mock.patch('tkinter.messagebox.showerror'):
            controller._handle_delete_done(3, ["err1", "err2"], "test.log", lang_dict)
        assert controller.is_complete is True
        # status_var에 오류 정보가 포함되어 있어야 함
        status = controller.status_var.get()
        assert status  # 오류 발생 후 비어있으면 안 됨
    finally:
        root.destroy()


# ===== Docstring Coverage Tests =====

class TestDocstringCoverage:
    """public 메서드에 docstring이 존재하는지 검증."""

    def test_controller_public_methods_have_docstrings(self):
        """모든 controller의 public 메서드에 docstring이 있는지 확인."""
        from src.resource_remover.controller import ResourceRemoverController
        
        public_methods = [
            m for m in dir(ResourceRemoverController)
            if not m.startswith('_') and callable(getattr(ResourceRemoverController, m))
        ]
        
        for method_name in public_methods:
            method = getattr(ResourceRemoverController, method_name)
            assert method.__doc__ is not None, (
                f"ResourceRemoverController.{method_name}() is missing a docstring"
            )

# ===== RenamerController Tests =====

def test_renamer_controller_get_lang_dict():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        from src.renamer.controller import RenamerController
        controller = RenamerController(root, app_lang_var=lang_var)

        assert controller.current_lang == 'ko'
        controller.set_language('en')
        assert controller.current_lang == 'en'
    finally:
        root.destroy()

# ===== AVConverterController Tests =====

def test_av_converter_controller_cleanup():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        from src.av_converter.controller import AVConverterController
        controller = AVConverterController(root, app_lang_var=lang_var)
        
        assert controller.log_queue is not None
        controller.cleanup()
    finally:
        root.destroy()

# ===== StoryViewerController Tests =====

def test_story_viewer_controller_clear_workspace():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        frame = ttk.Frame(root)
        from src.story_viewer.controller import StoryViewerController
        controller = StoryViewerController(frame, root, app_lang_var=lang_var)
        
        controller.all_files = {"test.json": "path"}
        controller.db_check_done = True
        controller._clear_workspace()
        assert len(controller.all_files) == 0
        assert controller.db_check_done is False
    finally:
        root.destroy()

# ===== AssetExtractorController Tests =====

def test_asset_extractor_controller_base_state():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.withdraw()
    try:
        lang_var = tk.StringVar(value='ko')
        frame = ttk.Frame(root)
        from src.unity_converter.controller import AssetExtractorController
        controller = AssetExtractorController(frame, root, app_lang_var=lang_var)
        
        assert controller.cancel_token.is_cancelled is False
        
        controller.asset_type_vars = {
            'Texture2D': tk.BooleanVar(value=True),
            'Sprite': tk.BooleanVar(value=True)
        }
        controller.deselect_all_types()
        assert not controller.asset_type_vars['Texture2D'].get()
        assert not controller.asset_type_vars['Sprite'].get()
    finally:
        root.destroy()
