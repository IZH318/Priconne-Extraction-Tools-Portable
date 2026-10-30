# 프린세스 커넥트! Re:Dive 종합 리소스 추출 도구

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.14.9-3776AB?logo=python&logoColor=white" alt="Python 3.14.9">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white" alt="Platform Windows">
  <img src="https://img.shields.io/badge/Language-KO%20%C2%B7%20EN%20%C2%B7%20JA-8A2BE2" alt="Languages KO EN JA">
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="License GPL-3.0">
  <img src="https://img.shields.io/badge/Version-3.0.1-orange" alt="Version 3.0.1">
</p>

<p align="center">
  <strong>게임 '프린세스 커넥트! Re:Dive'의 클라이언트 파일을 분석해,<br>
  각종 리소스를 추출, 변환하는 올인원 GUI 도구 모음입니다.</strong>
</p>

<br>

명령어 없이, 화면에서 클릭만으로 게임 리소스를 꺼내고 변환할 수 있습니다. <br>

매니페스트 이름 복원부터 `.unity3d` 에셋 추출, 오디오, 비디오 변환, 스토리 데이터 열람, 원본 파일 정리까지 다섯 가지 작업을 한 창의 탭에서 처리합니다. <br>

데이터 마이닝이나 팬 창작, 또는 게임 내부를 살펴보고 싶은 분들을 위해 만들었습니다. <br>
(\* 아직 발견하지 못한 오류가 있을 수 있습니다.)

<br><br>

## 🔍 주요 기능

- **`01. Manifest File Renamer`**
    - **이름 복원**: 파일명을 `manifest.db`의 해시와 대조해 원래 이름으로 되돌립니다. 이름으로 안 맞으면 `xxHash64`, `MD5` 콘텐츠 해시로 한 번 더 대조합니다.
    - **예외 처리**: DB에 없는 매니페스트 파일은 첫 줄 시그니처를 보고 `bdl_assetmanifest` 같은 이름으로 추정합니다.
    - **병렬 처리, 로그**: 여러 스레드로 처리하고, 진행률과 로그를 창에 실시간으로 보여줍니다.

- **`02. unity3d File Converter`**
    - **병렬 처리**: `.unity3d` 파일을 여러 프로세스로 나눠 처리합니다. 진행 중 취소할 수 있습니다.
    - **에셋 추출**: 텍스처, 스프라이트, 메시, 오디오, 셰이더, 폰트, 애니메이션, 비디오, `MonoBehaviour`, `TextAsset`(스토리 데이터 포함)을 자동으로 골라 추출하고, 그 밖의 타입은 `TypeTree` JSON으로 저장합니다.
    - **에셋 브라우저**: 번들 하나를 열어 내부 에셋을 트리로 훑어보고, 더블클릭하면 이미지, 오디오, 폰트, 메시, 셰이더, 스토리 데이터를 바로 미리 봅니다.
    - **3D 모델**: 압축 메시(`m_CompressedMesh`)를 풀어 `.obj`와 `.mtl`을 함께 생성합니다.
    - **출력 정리**: `Textures`, `Meshes`, `Audio` 식으로 타입별 폴더에 나눠 담고, 이름이 겹치면 `PathID`를 붙여 구분합니다.
    - **옵션**: Unity 버전은 프리셋(`2021.3.20f1`, `6000.0.58`)에서 고르거나 직접 넣을 수 있고, 추출할 에셋 종류도 체크박스로 고릅니다.

- **`03. Audio / Video Converter`**
    - **비디오, 오디오**: `.usm` → `.mp4`, `.awb` → `.wav` 변환을 탭으로 나눠 처리합니다.
    - **도구 자동 준비**: 온라인에선 `FFmpeg`, `UsmToolkit`, `vgmstream`과 **.NET Core 3.1 런타임**까지 자동으로 내려받아 준비합니다.
    - **오디오 트랙**: `.awb` 안의 트랙을 읽어, 트랙 이름이 있으면 파일명으로 쓰고 없으면 번호를 붙입니다.
    - **미리보기, 덮어쓰기**: 우클릭으로 변환 결과를 미리 재생해 보고, 기존 파일 덮어쓰기 여부를 고릅니다.
    - **버전 안내**: FFmpeg 버전을 점검해 7.1.1 설치를 안내합니다(세션당 1회). 오디오는 입력 파일별 하위 폴더에 트랙별 `.wav`로 저장합니다.

- **`04. storydata Viewer`**
    - **뷰어**: JSON 스토리 데이터를 구문 강조로 보여줘 Scene 헤더, 캐릭터, 대사를 구분합니다. 손상된 파일은 실패 로그로 자동 저장합니다.
    - **대본 모드**: 소설, 대본처럼 렌더링하고, 분기, 합류, 중첩 분기 들여쓰기, 루프/전환 씬, 인게임 무비, 스틸컷을 표시합니다.
    - **검색**: 캐릭터, 대사, BGM 등으로 복합 검색하고, 게임 DB(`master_jp.db` 등)와 연동해 이벤트 스토리를 이름으로 찾습니다.
    - **내보내기**: 스토리 데이터(TXT, Markdown), 캐릭터, BGM, 배경, 보이스, 파일명 목록, 서버별 이벤트 목록을 골라 내보내거나 클립보드로 복사합니다.

- **`05. Original Resource Remover`**
    - **원본 삭제**: 추출이 끝난 뒤 남은 원본 파일(`.unity3d`, `.acb`, `.awb`, `.usm`)을 카테고리별로 지웁니다.
    - **안전 삭제**: 기본은 휴지통으로 이동하고, 500개 이상이면 `DELETE`를 입력해 한 번 더 확인합니다.
    - **보호, 로그**: 개발, 시스템 폴더는 건너뛰고, 대상 경로 밖 파일은 손대지 않습니다. 삭제 내역은 `DeletionLog`로 남깁니다.

<br><br>

## 🔄 업데이트 내역

### v3.0.1 (2026-10-30)

`03. Audio / Video Converter` 의 오디오 변환 안정성을 보강한 수정 업데이트입니다.

- #### **🎧 오디오 변환 안정성**
    - **타임아웃 연장**: 오디오 변환·미리보기 기본 타임아웃을 60초 → **300초**로 늘림. 다중 작업 시 디스크·백신 부하로 일부 파일이 간헐적으로 타임아웃되던 문제를 완화.
    - **자동 재시도**: 오디오 스트림 디코딩이 타임아웃되면 **최대 5회** 자동 재시도하고, 재시도 전 불완전한 출력 파일을 정리.
    - **환경변수**: `PRICONNE_AUDIO_TIMEOUT`, `PRICONNE_PREVIEW_TIMEOUT` 로 계속 조정 가능.

<br>

### v3.0.0 (2026-10-30)

도구들을 하나의 앱으로 합치고 내부 구조를 다시 짠 메이저 업데이트입니다. v2.0.0 이후 바뀐 점을 정리했습니다.

- #### **🚀 공통 (아키텍처, 인프라)**
    - **단일 GUI 런처(EntryPoint)**: 흩어져 있던 실행 스크립트를 없애고, 5개 도구를 한 창의 탭으로 합침.
    - **MVC 전환, 계층 분리(SoC)**: GUI 레이어를 `Controller`/`View`로 나누고 `gui.py`는 얇은 래퍼로 정리. 커진 컨트롤러 로직은 여러 서브 서비스로 분리.
    - **의존성 주입(DI) 단일화**: `SharedDependencies`(불변 데이터클래스)를 두고 `SharedState`를 걷어냄. 서비스는 생성자 주입만 사용.
    - **공통 Mixin**: `QueuePollingMixin`(큐 폴링), `FileListMixin`(드래그 앤 드롭, 파일 목록), 로그 재렌더링(`redraw_all_logs`) 정리.
    - **큐 이벤트 타입화**: 워커↔GUI 통신을 `LogEvent`/`ProgressEvent`/`CompletionEvent` 객체로 통일. `__EXTRACTION_DONE__` 신호로 크로스 스레드 레이스 차단.
    - **다국어(i18n) 통합**: 언어 리소스를 `src/languages.json` 하나로 모으고, 언어를 바꾸면 전 탭 UI, 로그를 다시 그림. (한국어, 영어, 일본어, About 창은 영문 고정)
    - **진단 시스템**: `Breadcrumbs`로 실행 흐름을 추적하고, 도메인 예외(`src.exceptions`)와 크래시 리포트(`AppLog`/`ErrorLog`/`*Log`)를 추가.
    - **상수 지연 평가**: PEP 562 `__getattr__`로 URL, 타임아웃 상수를 늦게 읽고, `PRICONNE_*` 환경변수로 덮어쓰기. `MappingProxyType`으로 불변화.
    - **타입, 표준화**: `TabType` 등 타입을 조이고 `ModuleController` 프로토콜을 런타임에 검증. `__future__.annotations` 적용, PyInstaller 경로 자동 감지.

- #### **⚡ 성능, 안정성**
    - **스키마 디스크 캐시**: 역난독화 결과를 `schema_cache.json`에 저장해, 다음 실행에서 같은 분석을 다시 하지 않음. 웜 스타트가 훨씬 빨라짐.
    - **SQLite 연결 풀링**: 스레드별 읽기 전용 연결(`get_readonly_connection`)과 `mode=ro`로 조회 부담을 줄이고, 파일 락, 연결 누수도 차단.
    - **단일 I/O 듀얼 해시**: 한 번 읽어 `xxHash64`, `MD5`를 동시에 계산해, 같은 파일을 두 번 읽지 않도록 함. 해시 청크는 4KB → 64KB로 키움.
    - **적응형 폴링, UI 마샬링**: 유휴 시 간격을 늘리는 Backoff 폴링과 UI 콜백 큐(`post_to_ui`)로 응답성, CPU 효율 개선.
    - **병렬 스키마 분석, 듀얼 트랙 로딩**: 서버 스키마를 여러 프로세스로 병렬 처리하고, JSON 파싱과 DB 분석을 동시에 진행해 렌더링은 한 번만.
    - **즉시 복원 캐시**: 서버별 타이틀 캐시로 JP ↔ KR 전환 시 DB를 다시 조회하지 않고 바로 복원.
    - **메모리, 로딩 최적화**: 스토리 데이터 LRU 캐시, `UnityPy`, `Manager/Queue` 지연 로딩, 로더 메모리 누수 수정.
    - **안전한 종료**: 종료 시 자식 프로세스 트리를 정리(`terminate_all`)하고 스레드, 프로세스 풀을 바로 셧다운. PID로 잔여 임시 파일을 회수.
    - **IPC, 임시 폴더 격리**: PID별 세션 임시 폴더로 분리, `stdin` 차단으로 무한 프리징 방지, 이전 세션 잔여 폴더 정리.

- #### **🛡️ 보안**
    - **Zip-Slip, 심볼릭 링크 방어**: `safe_extract`(`zip_safe.py`)를 모든 해제 경로에 적용.
    - **SQL 식별자 화이트리스트**: 스토리 DB 쿼리 식별자를 검증해 인젝션 위험 차단.
    - **다운로드 무결성**: .NET 런타임 SHA-512 검증, ZIP 무결성(매직 바이트, 한도) 검사, `.part → 검증 → os.replace` 원자적 저장.
    - **파일명 새니타이징**: 금지 문자 치환(미디어, 스토리는 전각 치환), 예약명(`CON`/`NUL` 등) 처리, 중복 파일명 방어.
    - **개발 환경 보호**: 삭제기에서 개발, 시스템 폴더(`_PROTECTED_DIRS`)를 건너뛰고, 대상 경로 밖은 손대지 않음.

- #### **🧩 도구별 상세**
    - **`01. Manifest File Renamer`**
        - 텍스트 매니페스트(`manifest/`) 지원. 파일명, stem, 콘텐츠(`xxHash64`, `MD5`) 다단계 대조.
        - `manifest.db`를 우선 쓰고, DB에 없는 매니페스트는 첫 줄 시그니처로 추정.
        - 스레드 동기화(`_rename_lock`), 동일 경로 스킵, 드라이브 간 이동(`shutil.move`), 중복 `_(Duplicate_N)`, 성공/부분성공/실패 진행률.
        - 증분 로깅(`append_log`)으로 대량 작업 시 UI 멈춤 해소. 에러 로그 경로는 `get_application_base_path()`로 통일.

    - **`02. unity3d File Converter`**
        - **에셋 브라우저**: 우클릭으로 번들 내부를 트리로 보고, 여러 타입(Texture2DArray, Font, Mesh, Shader, MonoBehaviour, StoryData 등) 미리보기.
        - 압축 메시(`m_CompressedMesh`)와 `.obj`+`.mtl` 연동, `PathID` 충돌 시 고유 파일명, 실패 시 원본 바이너리 저장.
        - 멀티프로세스 추출(`ProcessPoolExecutor`). 취소 시 워커 즉시 종료, 완료 이벤트 보장.
        - `UnityPy` 지연 로딩, 번들 로드, 이름 계산 헬퍼(`asset_reader`), O(1) 디스패치 테이블, 브라우저 에러 로그 연동.

    - **`03. Audio / Video Converter`**
        - **도구 자동 준비(`ToolPipelineManager`)**: `UsmToolkit`, `vgmstream`, `FFmpeg`를 순서대로 받아 검사, 설치하고, 미리보기 때 빠진 도구를 바로 받아옴.
        - **.NET Core 3.1 로컬 무설치 런타임**: 시스템 런타임을 먼저 찾고, 없으면 x64 런타임(3.1.32)을 SHA-512 검증 후 풀어 `usmtoolkit/dotnet`에 둠. `DOTNET_ROOT`, `DOTNET_MULTILEVEL_LOOKUP=0` 격리 주입, `DOTNET_ROLL_FORWARD=Major` 상시 주입.
        - **버전 관리**: FFmpeg 7.1.1 권장(버전 마커, 4.4 이상 허용), vgmstream r2168, UsmToolkit 기본 `config` 유지, 버전 마커 경로 격리.
        - **미디어 미리보기**: AWB 멀티트랙 선택 재생, USM 임시 트랜스코딩 즉시 재생, 실패 시 에러 로그.
        - **UX**: 드래그 앤 드롭, 변환 중 목록 조작(DnD/우클릭/삭제) 차단, 완료, 취소 라벨 유지, 오디오 덮어쓰기 옵션, 프로세스 타임아웃.
        - **오디오 처리**: 스트림 일괄 파싱, 금지 문자 전각 치환, 중복 스템 해시 접미사, 완료, 유효 파일 스킵, 실패 결과 `.partial` 격리.
        - **비디오 인코딩**: `libx264`(crf 14), AAC(320k).

    - **`04. storydata Viewer`**
        - **대본 모드**: 분기, 합류 트리, 중첩 분기 들여쓰기, 분기 목적지 자동 계산, 루프/전환 씬, 인게임 무비, 스틸컷 렌더링.
        - **스키마 역난독화 엔진**: 테이블, 컬럼 해시를 자동 분석, 매핑, 다중 베이스라인 리졸버, 계층형 `db_config`(stories/events/minigames/system), 런타임 정규화 어댑터.
        - **타이틀 매핑 체인**: 스토리 상세, 신뢰도, 루나의 탑, 퀘스트, 생일, 알케스 연금당, 만우절 레이드(sekai), 이벤트 톱 토크, 이벤트 보스전, 이벤트 미니게임, 왕도종말결전, 우회로 배틀까지 단계적으로 매핑.
        - **검색**: 다조건 검색 + 디바운스 빠른 필터, 언어 비종속 화자 판별, 이벤트 DB 서브쿼리.
        - **내보내기**: 스토리(TXT, Markdown), 캐릭터, BGM, 배경, 보이스, 파일명 목록, 서버별 이벤트 목록, 단일 항목 창, 진행률, 취소 팝업, 클립보드 복사. 보기 모드(대본/간단/상세)와 파일명 규칙 선택.
        - **UX**: 표시 모드(`[ID]`/제목), 중복 제목 ID 병기, 다중 선택(EXTENDED), 우클릭 메뉴, KR 서버 2024-07-25 안내 팝업(세션당 1회), DB 자동 다운로드, 무결성 검사.

    - **`05. Original Resource Remover`**
        - 원본 파일(`.unity3d`, `.acb`, `.awb`, `.usm`)을 카테고리별로 삭제.
        - 기본은 휴지통, 영구 삭제도 선택 가능. 2단계 확인, 500개 이상은 `DELETE` 입력.
        - 삭제 대상 폴더 직접 선택, 개발, 시스템 폴더 보호, 실시간 취소, `DeletionLog` 감사 로그.

- #### **🔧 기타 변경 사항**
    - **빌드, 환경**: Python 3.14.9로 이전, `run.bat` 하나로 버전 확인, 가상환경 생성, 오프라인 패키지 설치, 실행까지 처리. Windows on ARM(64비트 호환) 대응, GitHub Actions CI(`ruff`/`mypy`/`unittest`).
    - **프로젝트 설정**: `pyproject.toml`(엄격 Mypy/Ruff), `.editorconfig`, `.gitattributes`, `.gitignore` 추가.
    - **정리**: 미사용 메서드, 예외, 상수, 임포트 삭제, `show_about_info()` 잔재 제거, `lang_types.py`(517줄) 삭제 후 `pick_language`/`format_text`로 대체.
    - **문서, 표준**: README 런타임 표기 갱신, 독스트링 정리, 로그, 예외 메시지 영문 통일, `DEFAULT_LANG(en)` 폴백.

<br>

<details>
<summary>📜 이전 업데이트 내역 - 클릭하여 열기</summary>

> <details>
> <summary>v2.0.0 (2025-07-26)</summary>
>
> 이번 업데이트는 모든 도구를 CLI에서 GUI로 전환하고, 성능과 사용자 경험을 극대화하는 데 중점을 둔 대규모 리팩토링입니다.
>
> - #### **🚀 공통 업데이트 내역**
>     - **GUI 도입**: 모든 도구가 `Tkinter` 기반의 GUI 애플리케이션으로 전환되어, 더 이상 명령어를 입력할 필요 없이 직관적인 조작이 가능해졌습니다.
>     - **비동기 처리 및 병렬화로 성능 극대화**: `threading`과 `concurrent.futures`를 도입하여 파일 처리 중 UI가 멈추는 현상을 해결하고, 멀티코어를 활용하여 작업 속도를 크게 향상시켰습니다.
>     - **다국어 지원 (i18n)**: **한국어, 영어, 일본어**를 지원하며, 메뉴를 통해 실시간으로 언어를 변경할 수 있습니다.
>     - **실시간 로그 및 상세 피드백**: 모든 작업 과정은 GUI 내 로그 창에 타임스탬프와 함께 실시간으로 기록됩니다.
>     - **견고한 소프트웨어 아키텍처**: 모든 코드를 UI와 로직으로 분리된 객체 지향(OOP) 구조로 재설계하여 안정성과 유지보수성을 높였습니다.
> - #### **📂 파일별 상세 업데이트 내역**
>     - **`01. Manifest File Renamer`**
>         - **피드백**: 실시간 로그 창과 Progress Bar를 통해 작업 진행 상태를 시각적으로 명확하게 표시.
>         - **프로세스**: 파일 이름 변경 작업을 백그라운드 스레드에서 처리하여 UI 응답성 유지.
>         - **예외 처리**: 해시 불일치 시, 파일 내용을 분석하여 `assetmanifest` 등을 추론하는 고급 예외 처리 로직 추가.
>     - **`02. unity3d File Converter`**
>         - **성능**: **멀티프로세스 병렬 처리**를 도입하여 대용량 `.unity3d` 파일 변환 속도를 극대화.
>         - **로그 시스템**: **로그 레벨(SUCCESS, WARNING, ERROR)에 따라 배경색과 글자색을 다르게 표시**하여 가독성을 크게 향상.
>         - **메시 추출 기능 강화**: 압축된 메시(`m_CompressedMesh`)를 완벽하게 지원하며, 정점 법선(Normal)을 수동으로 계산하고 **`.mtl` 재질 파일을 자동으로 생성**하여 3D 모델의 완성도를 높임.
>         - **파일 관리**: 에셋 타입별(`Textures`, `Meshes` 등)로 폴더를 자동 생성하며, 파일명 충돌 시 `PathID`를 이용해 고유한 이름 부여.
>     - **`03. Audio Video Converter` (통합)**
>         - **통합**: 기존의 오디오, 비디오 변환기를 **탭으로 구분된 단일 GUI 앱**으로 통합.
>         - **의존성 관리**: **FFmpeg 자동 다운로드 및 설치 기능**이 내장되어 사용자가 수동으로 설치할 필요가 없음.
>         - **오디오 처리**: `.awb` 파일 내의 모든 오디오 스트림(트랙)을 분석하고, 각 스트림의 **고유 이름을 찾아 파일명으로 사용**하여 정리 편의성 증대.
>         - **프로세스**: `subprocess.run`을 사용하여 외부 도구의 출력을 완벽하게 캡처하고 상세한 로그를 제공.
>     - **`04. storydata Viewer` (통합 및 기능 확장)**
>         - **핵심 기능**: 단순 정보 추출에서 벗어나, `storydata`를 **직접 보고 분석**하는 **완전한 뷰어 애플리케이션**으로 재탄생.
>         - **데이터 표시**: Scene 헤더, Key, 대사 등을 **구문 강조(Syntax Highlighting)**하여 가독성 극대화.
>         - **고급 검색**: 파일명, 캐릭터, 대사 등 복합 조건 검색 및 **DB 연동을 통한 이벤트 스토리 검색** 기능 추가.
>         - **내보내기**: 스토리 데이터, 각종 목록, **서버별 이벤트 목록** 등 원하는 데이터를 선택하여 한 번에 내보내기 가능.
>
> </details>
> <br>
> <details>
> <summary>v1.0.1 (2024-06-02)</summary>
>
> - **수정**
>     - 필수 필요 소프트웨어 도구 첨부 (\*.zip 파일 내 포함 됨)
>     - usmtoolkit 포함
>     - 보다 편하게 Python Package를 설치할 수 있도록 배치파일(\*.bat)로 구성
>     - 각종 Python Script에 안내 창 기능 추가
>     - 캐릭터 이름을 보다 편하게 추출할 수 있도록 '05. Character List Export.py' 제작
>     - 추출 한 스토리데이터에서 찾고자 하는 캐릭터 명과 연결 돼 있는 Vocal Resource, Dialog 정보를 보다 쉽게 검색할 수 있도록 '06. Vocal Resource Info Export.py' 제작
>     - 원본 Resource 파일을 보다 편하게 삭제할 수 있도록 '07. Original Resource Remover.bat ' 제작
>     - manifest 파일 중 일부 항목 예외 처리되지 않는 오류 수정
>     - 중복 파일이 아닌 파일 이름에 (Duplicate\_{counter}) 가 처리되는 오류 수정
> - **기타**
>     - `프린세스 커넥트! Re:Dive (JP) Asset 추출 도구` 게시
>
> </details>

</details>

<br><br>

## 💾 다운로드 및 요구사항

[<img width="128" height="128" alt="icon_item_91001" src="https://github.com/user-attachments/assets/68d9bbc3-3203-4890-ab47-edf1d01b982a" />](https://github.com/IZH318/Priconne-Extraction-Tools-Portable/releases)

### ※ 최신 버전은 상단의 쥬얼 아이콘을 클릭하거나, 본 저장소의 Releases 페이지에서 내려받습니다. <br><br>

**💡 설치 안내**

- **온라인 환경 (별도 준비 불필요)**:
    - Releases 페이지의 **`Source code (zip)`** 파일만 내려받아 원하는 위치에 압축을 풀면 됩니다. (이 폴더가 실행 위치)
    - 압축을 푼 폴더에서 `run.bat`을 실행하면 PC 환경(32/64)에 맞는 Python 3.14.9를 자동으로 설치하고, 가상환경과 패키지를 준비한 뒤 프로그램을 실행합니다.
    - 변환 도구(`FFmpeg`, `UsmToolkit`, `vgmstream`, `.NET Runtime`)는 처음 변환할 때, 스토리 DB(`master_jp.db`, `master_kr.db`)는 필요할 때 자동으로 내려받습니다.
- **오프라인 환경 (수동 준비 필요)**:
    - 인터넷이 안 되면 `run.bat`이 자동으로 받지 못하므로, 아래 3가지를 함께 내려받아 준비합니다.
        1. **`Source code (zip)`** — 프로그램 본체 (원하는 위치에 압축 풀기)
        2. **`Essential Software Pack (x86_x64).zip`** — Python 3.14.9 설치 파일, .NET Runtime 3.1.32, K-Lite Codec Pack, `usmtoolkit` 폴더
        3. **`master_jp.db`, `master_kr.db`** — 스토리 DB (다운로드는 하단 표 참고)
    - 팩의 설치 파일로 Python, .NET Runtime, K-Lite를 설치한 뒤, 팩의 `usmtoolkit` 폴더와 `master_jp.db`, `master_kr.db`를 `run.bat`, `main.py`와 같은 위치에 둡니다. (Python은 3.14.9, 기본 설치 경로 유지) <br><br>

    **`Essential Software Pack (x86_x64).zip`을 사용하지 않고 개별 다운로드할 경우, 아래 표의 설치, 배치 방법을 참고합니다.**

    | 소프트웨어                                  |                                           다운로드                                           |   <nobr>구분</nobr>   | 용도                                                                                                                                                                                           |
    | :------------------------------------------ | :------------------------------------------------------------------------------------------: | :-------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
    | <nobr>`Python 3.14.9`</nobr>                |              [Download](https://www.python.org/downloads/release/python-3149/)               | <nobr>**필수**</nobr> | GUI 애플리케이션을 돌리기 위한 런타임 <br>└ 설치 경로는 기본값 그대로 두기                                                                                                                     |
    | <nobr>`.NET Core 3.1`</nobr>                |              [Download](https://dotnet.microsoft.com/en-us/download/dotnet/3.1)              |   <nobr>선택</nobr>   | `03. Audio / Video Converter`의 비디오 변환(UsmToolkit 실행)에 필요 <br>└ 다운로드 페이지에서 `Run apps - Runtime` → `ASP.NET Core Runtime` → `Windows` → `Installers`(32/64) 항목을 받아 설치 |
    | <nobr>`FFmpeg 7.1.1`</nobr>                 |             [Download](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1)              |   <nobr>선택</nobr>   | `03. Audio / Video Converter`의 비디오 변환(인코딩)에 필요 <br>└ `ffmpeg-7.1.1-essentials_build.zip`을 받아 압축을 풀고, 안에 있는 `bin\ffmpeg.exe`를 `usmtoolkit` 폴더에 넣기                 |
    | <nobr>`UsmToolkit 0.2`</nobr>               |      [Download](https://github.com/Rikux3/UsmToolkit/releases/download/0.2/publish.zip)      |   <nobr>선택</nobr>   | `03. Audio / Video Converter`의 비디오 변환에 필요 <br>└ `publish.zip`을 받아 압축을 풀고, 풀린 폴더 이름을 `usmtoolkit`으로 바꾼 뒤 `run.bat`, `main.py`와 같은 위치에 두기                   |
    | <nobr>`vgmstream r2168`</nobr>              | [Download](https://github.com/vgmstream/vgmstream/releases/download/r2168/vgmstream-win.zip) |   <nobr>선택</nobr>   | `03. Audio / Video Converter`의 오디오 변환에 필요 <br>└ `vgmstream-win.zip`을 받아 압축을 풀고, 풀린 폴더 이름을 `vgmstream`으로 바꾼 뒤 `usmtoolkit` 폴더 안에 두기                          |
    | <nobr>`K-Lite Codec Pack`</nobr>            |          [Download](https://codecguide.com/download_k-lite_codec_pack_standard.htm)          |   <nobr>선택</nobr>   | 미디어 파일(.wav, .mp4) 재생이 안 될 때 설치 <br>└ 기본 설정으로 설치                                                                                                                          |
    | <nobr>`master_jp.db`, `master_kr.db`</nobr> |                   [Download](https://github.com/Expugn/priconne-database)                    |   <nobr>선택</nobr>   | 스토리 제목, 이벤트 검색용 DB <br>└ 받은 파일을 `run.bat`, `main.py` 파일과 같은 위치에 두기 (`src/` DB는 기본 포함)                                                                           |

<br><br>

## ❗ 주의 사항 ❗

- **모든 내용은 2026-10-30 JP, KR 서버 업데이트 기준이며, 작업 시점 또는 클라이언트 버전에 따라 결과가 다를 수 있습니다.**
- **추출된 리소스의 총 용량은 수십 GB에 달할 수 있으니, 작업 전에 저장 장치의 여유 공간을 반드시 확인하시기 바랍니다.**
- **아래 '지금까지 발견된 문제'를 미리 확인해 두면, 작업 중 문제가 생겼을 때 대처하기 수월합니다.**

> <details>
>   <summary>📛 지금까지 발견된 문제</summary>
>
> `01. 한국 서버 클라이언트 일부 *.usm 파일 소리 깨짐`<br>
> `\m\t` 폴더의 `*.usm` 파일 중 일부가 정상적으로 변환되지 않습니다.
>
> </details>

<br>

**클라이언트 또는 manifest.db에서 가리키는 각 폴더별 명칭은 아래 목록을 클릭하여 참고합니다.** <br>

> <details>
>   <summary>🗂 각 폴더별 이름</summary>
>
> ```
> \a = Asset (에셋)
> \b = BGM (배경음악)
> \s = SE (Sound Effect, 효과음)
> \v = Voice (음성)
> \m = Movie (영상)
> \t = Temp (임시)
> ```
>
> </details>

<br>

**각 manifest의 구조는 아래 목록을 클릭하여 참고합니다.** <br>

> <details>
>   <summary>🧾 All Manifests (Level 2)</summary>
>
> ※ 원본 국가나 작업 시점, 방법에 따라 일부 다르게 표기될 수 있습니다.
>
> ```
> 📁 PrincessConnectReDive
>   ├📁 a
>   │  ├📁 abyss
>   │  ├📁 alces
>   │  ├📁 all
>   │  ├📁 animation
>   │  ├📁 arcade
>   │  ├📁 atlasngui
>   │  ├📁 banner
>   │  ├📁 bdl
>   │  ├📁 bg
>   │  ├📁 caravan
>   │  ├📁 clanbattle
>   │  ├📁 colosseum
>   │  ├📁 comic
>   │  ├📁 consttext
>   │  ├📁 dailytask
>   │  ├📁 dome
>   │  ├📁 dungeon
>   │  ├📁 event
>   │  ├📁 font
>   │  ├📁 gacha
>   │  ├📁 howtoplay
>   │  ├📁 icon
>   │  ├📁 jukebox
>   │  ├📁 knightenhance
>   │  ├📁 lipsyncothers
>   │  ├📁 loginbonus
>   │  ├📁 masterdata
>   │  ├📁 minigame
>   │  ├📁 resourcedefine
>   │  ├📁 room
>   │  ├📁 roomeffect
>   │  ├📁 roomfinger
>   │  ├📁 roomgrid
>   │  ├📁 roomicon
>   │  ├📁 roomitem
>   │  ├📁 roomthumb
>   │  ├📁 shader
>   │  ├📁 spine
>   │  ├📁 storydata
>   │  ├📁 t
>   │  ├📁 talentquest
>   │  ├📁 travel
>   │  ├📁 unit
>   │  └📁 wac
>   ├📁 b
>   │  └📁 t
>   ├📁 m
>   │  └📁 t
>   ├📁 manifest
>   ├📁 s
>   │  └📁 t
>   └📁 v
>       └📁 t
> ```
>
> </details>

<br><br>

## ⏩ 사용 방법

### 1. 다운로드, 실행

- `Releases`에서 **`Source code (zip)`** 파일을 내려받아 원하는 위치에 압축을 풉니다. (이 폴더가 프로그램 본체, 실행 위치)
- 압축을 푼 폴더에서 **`run.bat`** 파일을 실행하면, `.venv`를 만들고 동봉된 `packages` 폴더의 패키지를 설치한 뒤 **통합 GUI**가 실행됩니다.
- Python 3.14.9와 변환 도구, 스토리 DB를 준비하는 방식은 환경에 따라 다릅니다.
    - **온라인**: `run.bat`이 Python 3.14.9를 자동으로 내려받아 설치하고, 변환 도구와 스토리 DB도 필요할 때 자동으로 준비됩니다. (수동 준비 불필요)
    - **오프라인**: 자동 내려받기가 안 되므로, `Essential Software Pack (x86_x64).zip`과 `master_jp.db`, `master_kr.db`를 함께 준비해 두어야 합니다. (`💾 다운로드 및 요구사항` 참고)

### 2. 클라이언트 파일 준비

- 안전한 작업을 위해, 게임 클라이언트 원본(`manifest.db`와 `a`, `b`, `m`, `s`, `v` 폴더)은 **백업(사본)을 따로 만들어** 두고 그 사본으로 작업합니다.
- 백업할 때는 원본의 **폴더 구조(경로)를 그대로 유지**해야 합니다. `manifest.db`와 `a`, `b`, `m`, `s`, `v` 폴더가 같은 상위 폴더 안에 함께 있어야 하며, 이름을 바꾸거나 옮기면 파일명 복원이 제대로 되지 않습니다.

### 3. 각 탭 사용법

- **`01. Manifest File Renamer`** (`[※] Manifest File Renamer` 탭)
    - '폴더 열기'로 게임 클라이언트 루트(`manifest.db`가 있는 폴더)를 지정한 뒤 '작업 시작'을 누릅니다. (작업 중에는 버튼이 비활성화됩니다.)
    - `manifest.db`를 기준으로 난독화된 파일명을 원래 이름으로 되돌립니다. DB에 없는 매니페스트는 파일 첫 줄 내용으로 이름을 추정합니다.
    - 진행률, 로그로 처리 현황을 확인하고, 처리하지 못한 파일은 `logs/RenamerLog_*.log`에 남깁니다.
    - 완료되면 `a`, `b`, `m`, `s`, `v` 폴더의 파일명이 원래대로 바뀝니다.

- **`02. unity3d File Converter`**
    - 왼쪽 목록에 입력 파일/폴더(보통 `a`)를 추가하고, 출력 폴더를 고릅니다. (드래그 앤 드롭 지원)
    - Unity 버전(`2021.3.20f1`, `6000.0.58` 또는 직접 입력)과 추출할 에셋 타입을 고릅니다(전체 선택/해제 가능).
    - '작업 시작'으로 추출하며, 진행 중 '취소'할 수 있습니다.
    - 목록에서 우클릭하면 '선택 항목 제거 / 전체 항목 제거 / 에셋 브라우저'가 나오고, `Delete` 키로도 제거합니다.
    - '에셋 브라우저'에서 번들 내부를 트리로 보고, 더블클릭으로 이미지, 오디오, 폰트, 메시, 셰이더, 스토리 데이터를 미리 봅니다.
    - 결과는 출력 폴더에 원본 경로 구조를 유지한 채 타입별 폴더로 정리되고, 이름이 겹치면 `PathID`가 붙습니다.

- **`03. Audio / Video Converter`**
    - 오디오 또는 비디오 탭을 고르고, 변환할 파일/폴더(비디오 `m`, 오디오 `b`, `s`, `v`)와 출력 폴더를 지정합니다.
    - '작업 시작'으로 변환하고, 진행 중 '취소'할 수 있으며 오디오 탭은 덮어쓰기 여부를 고릅니다.
    - 목록에서 우클릭하면 '선택 항목 제거 / 전체 항목 제거 / 미리보기'가 나옵니다. `.awb`는 트랙을 골라 재생하고, `.usm`은 임시 변환 후 재생합니다.
    - 변환 도구(`UsmToolkit`, `vgmstream`, `FFmpeg`, `.NET 런타임`)는 처음 사용할 때 자동 준비되고, 이미 변환된 파일은 건너뛰며 실패한 결과물은 `.partial`로 격리합니다.

- **`04. storydata Viewer`**
    - 파일 또는 폴더(`storydata_*.json`)를 엽니다.
    - 보기 모드를 고릅니다 — **대본**(소설/대본처럼 분기, 루프, 무비, 스틸컷 표시) / **간단** / **상세**.
    - 빠른 필터로 목록을 좁히고, '검색'에서 파일명, 제목, 캐릭터, 대사, BGM, 배경, 이벤트로 찾습니다.
    - '내보내기'로 스토리(TXT/Markdown), 목록(캐릭터/BGM/배경/보이스/파일명), 서버별 이벤트 목록을 저장하며, 보기 모드와 파일명 규칙을 고를 수 있습니다. '복사'로 본문을 클립보드에 담습니다.
    - 목록에서 여러 개 선택(Shift/Ctrl) 후 우클릭하면 '선택 항목 제거 / 전체 항목 제거 / 이 항목 내보내기'가 나옵니다.
    - '이벤트 스토리 검색'에는 `master_jp.db`/`master_kr.db`가 필요하고(없으면 자동 다운로드), KR 서버는 2024-07-25 기준 데이터까지만 공식 제목이 조회됩니다.

- **`05. Original Resource Remover`**
    - '폴더 선택'으로 대상 폴더를 고르고, 삭제할 카테고리(에셋 `.unity3d`, 오디오 `.acb`/`.awb`, 비디오 `.usm`)를 체크합니다.
    - '휴지통으로 이동'을 켜면 복구할 수 있고, 끄면 영구 삭제됩니다.
    - '리소스 삭제 시작' → 확인 창에서 승인합니다(500개 이상이면 `DELETE` 입력을 한 번 더 요구). 진행 중 '취소'할 수 있습니다.
    - 개발, 시스템 폴더는 건너뛰고 대상 밖 파일은 건드리지 않으며, 삭제 내역은 `logs/DeletionLog_*.log`에 남깁니다.

<br><br>

## 👏 Special Thanks To & References

이 프로젝트는 아래 오픈소스에서 많은 도움을 받았습니다. 먼저 만든 분들께 감사드립니다.

- **[lskyset/priconne-asset-extractor](https://github.com/lskyset/priconne-asset-extractor)**
    - 클라이언트에서 에셋을 꺼내는 구조를 잡을 때 참고했고, 이 프로젝트의 출발점이 되었습니다.
- **[toretate/PrincessTool](https://github.com/toretate/PrincessTool)**
    - 2024년에 파일명 해시 계산이 바뀐 부분을 정리할 때 참고했습니다.
    - (원본: **[AioiLight/PrincessTool](https://github.com/AioiLight/PrincessTool)**)
- **[aelurum/AssetStudio](https://github.com/aelurum/AssetStudio)**
    - Unity 에셋 파일 구조를 파악할 때 참고했습니다.
- **[K0lb3/UnityPy](https://github.com/K0lb3/UnityPy)**
    - `.unity3d` 번들에서 에셋을 읽어 옵니다.
- **[Rikux3/UsmToolkit](https://github.com/Rikux3/UsmToolkit)**
    - `.usm` 영상을 풀고 다시 인코딩합니다.
- **[vgmstream/vgmstream](https://github.com/vgmstream/vgmstream)**
    - `.acb`, `.awb` 오디오를 열어 트랙별로 뽑습니다.
- **[FFmpeg (GyanD/codexffmpeg)](https://github.com/GyanD/codexffmpeg)**
    - 영상, 음성 인코딩을 담당합니다.
- **[Expugn/priconne-database](https://github.com/Expugn/priconne-database)**
    - `master_jp.db`, `master_kr.db`(스토리 제목 등 데이터)를 제공합니다.

<br>

✨ Princess Connect! Re:Dive Game Users

<br>
