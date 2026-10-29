"""컨트롤러 공통 인터페이스 및 프로토콜 계약 모듈.

메인 런처(main.py)와 각 서브도구(renamer, unity_converter, av_converter 등) 컨트롤러 간
결합도 완화 및 타입 안전성 보장용 PEP 544 구조적 서브타이핑(Structural Subtyping) 프로토콜 정의.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModuleController(Protocol):
    """서브 도구 Controller 공통 수명주기 및 다국어 인터페이스.

    main.py 종료 루틴(on_closing) 및 다국어 갱신 시 구체 클래스 의존성 배제 및
    타입 안전 메서드 호출 보장.
    """

    def cleanup(self) -> None:
        """앱 종료 시 스레드, 서브프로세스 및 임시 리소스 정리."""
        ...

    def get_lang_dict(self) -> dict[str, str]:
        """현재 활성 언어 설정 대응 다국어 UI 번역 딕셔너리 반환.

        Returns:
            dict[str, str]: UI 위젯 키와 번역된 문자열 매핑.
        """
        ...


def validate_module_controller(obj: object) -> bool:
    """객체의 ModuleController 필수 메서드 시그니처 검증.

    호출자는 사전에 isinstance(obj, ModuleController) 검사를 완료한 객체만
    전달해야 한다. 본 함수는 프로토콜 준수 여부(isinstance)를 재검사하지 않고,
    inspect.signature 기반 필수 메서드(cleanup, get_lang_dict)의
    인자 개수(0개)와 호출 가능 여부 유효성 검증.

    Args:
        obj (object): ModuleController 프로토콜을 준수하는 것으로 가정된 컨트롤러 인스턴스.

    Returns:
        bool: 필수 메서드 파라미터 시그니처 일치 시 True, 미일치 시 False.
    """
    import inspect
    for name in ("cleanup", "get_lang_dict"):
        method = getattr(obj, name, None)
        if not callable(method):
            return False
        try:
            sig = inspect.signature(method)
        except (TypeError, ValueError):
            return False
        if name == "cleanup" and len(sig.parameters) != 0:
            return False
        if name == "get_lang_dict" and len(sig.parameters) != 0:
            return False
    return True

