# 프린세스 커넥트! Re:Dive 종합 리소스 추출 도구

<p align="center">
  <strong>게임 '프린세스 커넥트! Re:Dive'의 클라이언트 파일을 분석하고,<br>
  각종 리소스를 오프라인 환경에서 국가 서버에 상관없이 추출 및 변환하는 올인원 GUI 도구 모음입니다.</strong>
</p>
<br>

직관적인 그래픽 인터페이스를 통해 누구나 손쉽게 게임 리소스를 다룰 수 있습니다. <br>

이 프로젝트는 데이터 마이닝, 팬 창작 활동, 또는 단순히 게임의 내부를 탐구하고 싶은 모든 분들을 위해 만들어졌습니다. <br>
(* 미처 발견하지 못한 오류가 있을 수 있습니다.)

<br><br>


## 🔍 주요 기능

이 도구 모음은 복잡하고 파편화되었던 CLI 스크립트들을 **사용자 친화적인 단일 GUI 애플리케이션**들로 통합하여, 게임 리소스 추출 및 분석 작업을 직관적이고 효율적으로 만듭니다. <br>

각 도구는 독립적으로 실행되며 다음과 같은 기능을 제공합니다. <br>

-   **`01. Manifest File Renamer`**:
    -   **자동 해시 대조**: `manifest.db`를 기반으로 `MD5` 및 `xxHash64`를 사용하여 SHA1 파일명을 **원본 이름으로 변경**합니다.
    -   **지능형 예외 처리**: DB에 없는 매니페스트 파일의 경우, **파일 내용을 분석**하여 `bdl_assetmanifest` 등으로 추론하고 이름을 변경합니다.
    -   **실시간 피드백**: 모든 처리 과정을 로그 창에 상세히 기록하고, 진행률 표시줄을 통해 작업 상태를 시각적으로 보여줍니다.

-   **`02. unity3d File Converter`**:
    -   **멀티프로세스 병렬 처리**: 여러 CPU 코어를 동시에 활용하여 수천 개의 `.unity3d` 파일을 **압도적으로 빠른 속도**로 처리합니다.
    -   **고급 3D 모델 추출**: 압축된 메시(`m_CompressedMesh`)를 완벽하게 지원하며, 3D 모델의 재질 정보(`.mtl`)와 텍스처를 **자동으로 연결하여 추출**합니다.
    -   **체계적인 결과물 관리**: 추출된 모든 리소스는 `Textures`, `Meshes`, `Audio` 등 **에셋 타입에 따라 자동으로 폴더가 분류**되어 저장됩니다.
    -   **상세한 로그 시스템**: **성공, 경고, 오류** 등 로그 레벨에 따라 색상을 구분하여 표시하므로 문제 발생 시 원인을 쉽게 파악할 수 있습니다.

-   **`03. Audio Video Converter`**:
    -   **통합 인터페이스**: 비디오(`.usm` → `.mp4`)와 오디오(`.acb`, `.awb` → `.wav`) 변환 기능을 **탭으로 구분된 단일 앱**에서 모두 처리합니다.
    -   **의존성 자동 해결**: 변환에 필요한 `ffmpeg.exe`가 없을 경우, **자동으로 다운로드하고 설치**하여 사용자 준비 과정을 최소화합니다.
    -   **지능형 오디오 트랙 관리**: `.awb` 파일 내의 모든 오디오 트랙을 분석하고, 각 **트랙의 고유 이름을 찾아 파일명으로 사용**하여 정리 편의성을 극대화합니다.

-   **`04. storydata Viewer`**:
    -   **가독성 높은 뷰어**: JSON 형식의 스토리 데이터를 **구문 강조(Syntax Highlighting)**하여 Scene 헤더, 캐릭터, 대사 등을 명확하게 구분해 보여줍니다.
    -   **강력한 고급 검색**: 캐릭터, 대사, BGM 등 복합 조건 검색은 물론, **게임 DB 파일(`master_jp.db` 등)을 연동하여 특정 이벤트 스토리를 이름으로 검색**하는 고유 기능을 제공합니다.
    -   **다목적 내보내기**: 불러 온 파일 또는 검색한 결과를 바탕으로 **스토리 데이터, 각종 목록(캐릭터, BGM 등), 이벤트 목록**을 선택하여 내보낼 수 있습니다.

<br><br>


## 🔄 업데이트 내역

### v2.0.0 (2025-07-26)

이번 업데이트는 모든 도구를 CLI에서 GUI로 전환하고, 성능과 사용자 경험을 극대화하는 데 중점을 둔 대규모 리팩토링입니다.

-   #### **🚀 공통 업데이트 내역**
    -   **GUI 도입**: 모든 도구가 `Tkinter` 기반의 GUI 애플리케이션으로 전환되어, 더 이상 명령어를 입력할 필요 없이 직관적인 조작이 가능해졌습니다.
    -   **비동기 처리 및 병렬화로 성능 극대화**: `threading`과 `concurrent.futures`를 도입하여 파일 처리 중 UI가 멈추는 현상을 해결하고, 멀티코어를 활용하여 작업 속도를 크게 향상시켰습니다.
    -   **다국어 지원 (i18n)**: **한국어, 영어, 일본어**를 지원하며, 메뉴를 통해 실시간으로 언어를 변경할 수 있습니다.
    -   **실시간 로그 및 상세 피드백**: 모든 작업 과정은 GUI 내 로그 창에 타임스탬프와 함께 실시간으로 기록됩니다.
    -   **견고한 소프트웨어 아키텍처**: 모든 코드를 UI와 로직으로 분리된 객체 지향(OOP) 구조로 재설계하여 안정성과 유지보수성을 높였습니다.

-   #### **📂 파일별 상세 업데이트 내역**

    -   **`01. Manifest File Renamer`**
        -   **피드백**: 실시간 로그 창과 Progress Bar를 통해 작업 진행 상태를 시각적으로 명확하게 표시.
        -   **프로세스**: 파일 이름 변경 작업을 백그라운드 스레드에서 처리하여 UI 응답성 유지.
        -   **예외 처리**: 해시 불일치 시, 파일 내용을 분석하여 `assetmanifest` 등을 추론하는 고급 예외 처리 로직 추가.

    -   **`02. unity3d File Converter`**
        -   **성능**: **멀티프로세스 병렬 처리**를 도입하여 대용량 `.unity3d` 파일 변환 속도를 극대화.
        -   **로그 시스템**: **로그 레벨(SUCCESS, WARNING, ERROR)에 따라 배경색과 글자색을 다르게 표시**하여 가독성을 크게 향상.
        -   **메시 추출 기능 강화**: 압축된 메시(`m_CompressedMesh`)를 완벽하게 지원하며, 정점 법선(Normal)을 수동으로 계산하고 **`.mtl` 재질 파일을 자동으로 생성**하여 3D 모델의 완성도를 높임.
        -   **파일 관리**: 에셋 타입별(`Textures`, `Meshes` 등)로 폴더를 자동 생성하며, 파일명 충돌 시 `PathID`를 이용해 고유한 이름 부여.

    -   **`03. Audio Video Converter` (통합)**
        -   **통합**: 기존의 오디오, 비디오 변환기를 **탭으로 구분된 단일 GUI 앱**으로 통합.
        -   **의존성 관리**: **FFmpeg 자동 다운로드 및 설치 기능**이 내장되어 사용자가 수동으로 설치할 필요가 없음.
        -   **오디오 처리**: `.awb` 파일 내의 모든 오디오 스트림(트랙)을 분석하고, 각 스트림의 **고유 이름을 찾아 파일명으로 사용**하여 정리 편의성 증대.
        -   **프로세스**: `subprocess.run`을 사용하여 외부 도구의 출력을 완벽하게 캡처하고 상세한 로그를 제공.

    -   **`04. storydata Viewer` (통합 및 기능 확장)**
        -   **핵심 기능**: 단순 정보 추출에서 벗어나, `storydata`를 **직접 보고 분석**하는 **완전한 뷰어 애플리케이션**으로 재탄생.
        -   **데이터 표시**: Scene 헤더, Key, 대사 등을 **구문 강조(Syntax Highlighting)**하여 가독성 극대화.
        -   **고급 검색**: 파일명, 캐릭터, 대사 등 복합 조건 검색 및 **DB 연동을 통한 이벤트 스토리 검색** 기능 추가.
        -   **내보내기**: 스토리 데이터, 각종 목록, **서버별 이벤트 목록** 등 원하는 데이터를 선택하여 한 번에 내보내기 가능.

<br>

<details>
<summary>📜 이전 업데이트 내역 - 클릭하여 열기</summary>
<br>
<details>
<summary>v1.0.1 (2024-06-02)</summary>
  
  -   **수정**
      -   필수 필요 소프트웨어 도구 첨부 (*.zip 파일 내 포함 됨)
      -   usmtoolkit 포함
      -   보다 편하게 Python Package를 설치할 수 있도록 배치파일(*.bat)로 구성
      -   각종 Python Script에 안내 창 기능 추가
      -   캐릭터 이름을 보다 편하게 추출할 수 있도록 '05. Character List Export.py' 제작
      -   추출 한 스토리데이터에서 찾고자 하는 캐릭터 명과 연결 돼 있는 Vocal Resource, Dialog 정보를 보다 쉽게 검색할 수 있도록 '06. Vocal Resource Info Export.py' 제작
      -   원본 Resource 파일을 보다 편하게 삭제할 수 있도록 '07. Original Resource Remover.bat ' 제작
      -   manifest 파일 중 일부 항목 예외 처리되지 않는 오류 수정
      -   중복 파일이 아닌 파일 이름에 (Duplicate\_{counter}) 가 처리되는 오류 수정
  -   **기타**
      -   `프린세스 커넥트! Re:Dive (JP) Asset 추출 도구` 게시

</details>
</details>

<br><br>


## 💾 다운로드 및 요구사항
[<img width="128" height="128" alt="icon_item_91001" src="https://github.com/user-attachments/assets/68d9bbc3-3203-4890-ab47-edf1d01b982a" />](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/releases)

### ※ 추출 도구는 상단 쥬얼 아이콘을 클릭 또는 본 저장소의 Releases 페이지로 이동하여 다운로드 하십시오. <br><br>

| 소프트웨어 | URL | 필수여부 | 비고 |
| :--- | :--- | :--- | :--- |
| `Python 3.10+` | [Download](https://www.python.org/downloads/release/python-31011/) | **필수** | ◼ 모든 GUI 애플리케이션 실행에 필요합니다.<br>◼ **설치 시 'Add python.exe to PATH' 옵션을 반드시 체크해주세요.** |
| `.NET Runtime 3.1` | [Download](https://dotnet.microsoft.com/en-us/download/dotnet/3.1) | 선택 | ◼ `03. Audio Video Converter`의 일부 기능(UsmToolkit) 실행에 필요합니다. |
| `K-Lite Codec Pack` | [Download](https://codecguide.com/download_k-lite_codec_pack_standard.htm) | 선택 | ◼ 변환된 오디오(.wav) 및 비디오(.mp4) 파일이 정상적으로 재생되지 않을 경우 설치를 권장합니다. |

<br><br>


## ❗ 주의 사항 ❗

-   **모든 내용은 2025-07-25 JP, KR 서버 업데이트 기준이며, 작업 시점 또는 클라이언트 버전에 따라 결과가 다를 수 있습니다.**
-   **추출된 리소스의 총 용량은 수십 GB에 달할 수 있으니, 반드시 저장 장치의 여유 공간을 확인 후 작업하시기 바랍니다.**
-   발견된 문제를 미리 확인하여 작업 중 적절히 대처할 수 있도록 준비하십시오.

<details>
  <summary>📛 지금까지 발견 된 문제</summary><br>

`01. 한국 서버 클라이언트 일부 *.usm 파일 소리 깨짐`<br>
`\m\t` 폴더에 있는 *.usm 파일 중 일부 *.usm 파일이 정상적으로 변환되지 않음

<br>

</details>

<br>

**클라이언트 또는 manifest.db에서 가리키는 각 폴더별 명칭은 아래 목록을 클릭하여 참고하십시오.** <br>
<details>
  <summary>🗂 각 폴더별 이름</summary><br>

```
\a = Asset (에셋)
\b = BGM (배경음악)
\s = SE (Sound Effect, 효과음)
\v = Voice (음성)
\m = Movie (영상)
\t = Temp (임시)
```

</details>

<br>

**각 manifest의 구조는 아래 목록을 클릭하여 참고하십시오.** <br>
<details>
  <summary>🧾 All Manifests (Level 2)</summary><br>

※ 원본 국가, 작업하는 시점 또는 방법에 따라 일부 다르게 표기될 수 있음

```
📁 PrincessConnectReDive
  ├📁 a
  │  ├📁 abyss
  │  ├📁 alces
  │  ├📁 all
  │  ├📁 animation
  │  ├📁 arcade
  │  ├📁 atlasngui
  │  ├📁 banner
  │  ├📁 bdl
  │  ├📁 bg
  │  ├📁 caravan
  │  ├📁 clanbattle
  │  ├📁 colosseum
  │  ├📁 comic
  │  ├📁 consttext
  │  ├📁 dailytask
  │  ├📁 dome
  │  ├📁 dungeon
  │  ├📁 event
  │  ├📁 font
  │  ├📁 gacha
  │  ├📁 howtoplay
  │  ├📁 icon
  │  ├📁 jukebox
  │  ├📁 knightenhance
  │  ├📁 lipsyncothers
  │  ├📁 loginbonus
  │  ├📁 masterdata
  │  ├📁 minigame
  │  ├📁 resourcedefine
  │  ├📁 room
  │  ├📁 roomeffect
  │  ├📁 roomfinger
  │  ├📁 roomgrid
  │  ├📁 roomicon
  │  ├📁 roomitem
  │  ├📁 roomthumb
  │  ├📁 shader
  │  ├📁 spine
  │  ├📁 storydata
  │  ├📁 t
  │  ├📁 talentquest
  │  ├📁 travel
  │  ├📁 unit
  │  └📁 wac
  ├📁 b
  │  └📁 t
  ├📁 m
  │  └📁 t
  ├📁 manifest
  ├📁 s
  │  └📁 t
  └📁 v
      └📁 t
```

</details>

<br><br>


## ⏩ 사용 방법

01. `Releases`에서 최신 버전의 `Source code (zip)` 와 `Essential Software Pack (x64).zip` 파일을 다운로드 후 적절한 위치에 압축 해제합니다. <br><br><br>

02. `💾 다운로드 및 요구사항`를 참고하여 `Essential Software Pack (x64)`에 포함 된 설치 파일을 실행하여 소프트웨어를 설치합니다. <br><br><br>

03. `00. Install required Python packages.bat` 파일을 **더블 클릭하여 실행**하고, 필요한 파이썬 패키지들이 자동으로 설치될 때까지 기다립니다. <br><br><br>

04. 게임 클라이언트 원본(`manifest.db` 파일과 `a`, `b`, `m` 등의 폴더)을 압축 해제한 폴더 내로 **구조 그대로** 복사합니다. <br>
    <img width="640" height="480" alt="캡처_2025_07_26_03_21_53_278" src="https://github.com/user-attachments/assets/fdc6abbe-3f90-46f3-a04b-c3b61bd785d1" /> <br><br><br>

05. **`01. Manifest File Renamer.py`** 파일을 실행하고, '작업 시작' 버튼을 눌러 파일 이름 변경을 완료합니다. <br>
    ![ezgif-155a9328572149 (optimize)](https://github.com/user-attachments/assets/ed6af744-86b3-4af3-915c-ed9849cb346d) <br><br><br>

06. **`02. unity3d File Converter.py`** 파일을 실행합니다. '폴더 열기'로 `a` 폴더를 선택하고, 출력 폴더를 지정한 뒤 '작업 시작' 버튼을 눌러 에셋 추출을 진행합니다. <br><br>
    ![ezgif-1291b3399d49c2 (optimize)](https://github.com/user-attachments/assets/40540e1d-60f6-426e-843f-faae0e82bf89) <br>
    (📌 추출된 파일들은 지정한 출력 폴더 내에 원본 파일 경로 구조를 유지한 채로 `Textures`, `Meshes` 등 에셋 타입별 하위 폴더로 자동 정리됩니다.) <br><br><br>

07. **`03. Audio Video Converter.py`** 파일을 실행합니다. 각 탭에서 변환할 파일 또는 폴더(`m`, `b`, `s`, `v`)를 추가하고 출력 폴더를 지정한 후 '작업 시작' 버튼을 누릅니다. <br><br>
    (📌 **팁: 수동 FFmpeg 설정**) <br>
    인터넷 연결이 없거나 FFmpeg 자동 다운로드가 실패하는 경우, `Essential Software Pack (x64).zip`에 포함된 `ffmpeg.exe` 파일 또는 별도로 다운로드한 `ffmpeg.exe`를 `usmtoolkit` 폴더 (`UsmToolkit.exe`와 동일한 위치)에 직접 복사해주시면 됩니다.<br><br>
    ![ezgif-16fd5bf821c2ef (optimize)](https://github.com/user-attachments/assets/8bb53d24-bf7f-4ff7-a3be-039a7b6b412b) <br>
    (📌 비디오 파일 변환) <br><br>
    ![ezgif-1919cb217c87b0 (optimize)](https://github.com/user-attachments/assets/df9a12b2-cdeb-4bb7-83d3-8f3d89b9a5ec) <br>
    (📌 오디오 파일 변환) <br><br><br>

08. **(선택)** **`04. storydata Viewer.py`** 파일을 실행하여 추출된 스토리 데이터를 보거나, 고급 검색 및 데이터 목록을 내보낼 수 있습니다. <br>
    ![ezgif-1a9508af4d94a5 (optimize)](https://github.com/user-attachments/assets/6e0b0985-a318-4693-80ac-8b8cce85a225) <br>
    (📌 '이벤트 스토리 검색' 기능을 활용하려면, [Expugn/priconne-database](https://github.com/Expugn/priconne-database) 에서 `master_jp.db` (일본 서버) 또는 `master_kr.db` (한국 서버) 파일을 다운로드 받아 `04. storydata Viewer.py` 파일과 **동일한 폴더**에 위치시켜 주세요.) <br><br>
    ![ezgif-1180aa5676f9df (optimize)](https://github.com/user-attachments/assets/7cb0bcd6-d98f-47e1-9268-133f644948dd) <br>
    (📌 storydata 및 db 파일 기반 정보 내보내기) <br><br><br>

09. **(선택)** 모든 작업 완료 후 원본 리소스 파일을 제거하고 싶다면 **`05. Original Resource Remover.bat`** 파일을 실행합니다.

<br><br>


## 📝 해야 할 일 (TODO)
-   게임 출석
-   콧코로 수첩
-   지역
-   이벤트 스토리
-   던전
-   아레나, 프레나
-   클랜전

<br><br>


## 👏 Special Thanks To & References

✨ 이 프로젝트는 아래의 훌륭한 오픈소스 프로젝트들로부터 많은 영감과 도움을 받아 만들어졌습니다. 각 개발자분들께 깊은 감사를 드립니다.

-   **[lskyset/priconne-asset-extractor](https://github.com/lskyset/priconne-asset-extractor)**
    -   게임 에셋 추출 로직 및 초기 아이디어에 큰 영감을 주었습니다.
-   **[toretate/PrincessTool](https://github.com/toretate/PrincessTool)**
    -   2024년 파일명 Hash값 계산 방식 변경 방법에 대한 유용한 참고 자료가 되었습니다.
    -   (원본: **[AioiLight/PrincessTool](https://github.com/AioiLight/PrincessTool)**)
-   **[aelurum/AssetStudio](https://github.com/aelurum/AssetStudio)**
    -   Unity 에셋 파일 구조 이해 및 다양한 리소스 변환 방법에 대한 유용한 참고 자료가 되었습니다.

✨ Princess Connect! Re:Dive Game Users <br>
