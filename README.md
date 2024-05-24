# 프린세스 커넥트! Re:Dive (JP) Asset 추출 도구
게임 '프린세스 커넥트! Re:Dive'의 클라이언트 파일을 국가 상관 없이 Resource를 추출 및 변환하는 도구입니다. <BR>
(* 미처 발견하지 못한 오류가 있을 수 있습니다.)

<BR><BR><BR>

## 🔍 주요 기능
■ 클라이언트 파일이 있는 위치에서 스크립트를 실행하면 각 파일 이름을 원본 이름으로 변경 후 파일이 추출됩니다. <BR>
(* 확장자 별 변환 과정은 다음과 같습니다.)
  - *.unity3d -> *.png, *.txt
  - *.awb, *.acb -> *.wav
  - *.usm -> *.mp4
  - *storydata.bytes -> *.json

<BR><BR><BR>

## 💾 다운로드
[![icon_item_91001](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/89c074f2-f869-4377-8e10-fc6a1d7e5de4)](https://github.com/IZH318/priconne-asset-extractor/releases)
### ※ 추출 도구는 상단 쥬얼 아이콘을 클릭 또는 본 Repositories의 Releases로 이동하여 다운로드 하십시오. <br><br>
### ※ 본 도구를 사용할 때 필요한 모든 파일들은 zip 파일 내 `📁\01_Install` 폴더에 포함되어 있습니다. <BR>
***.zip 파일 내 제공 된 파일들을 사용하려는 경우 개별 다운로드 과정을 생략해도 되며, 제공 된 설치 파일들을 신뢰하지 않을 경우 아래 링크를 통해 개별 다운로드 하시기 바랍니다.** <BR>

| Program                                | URL                                                | 필수여부 | 비고                                                                                           |
|----------------------------------------|----------------------------------------------------|----------|------------------------------------------------------------------------------------------------|
| `Python 3.10.11`            | [Download](https://www.python.org/downloads/release/python-31011/)   | 필수     | ◼ Python Script 동작, 파이썬 3.10.xx 버전 중 아무거나 사용 가능<BR>◼ 단, 3.10.xx 버전이 아닌 다른 버전은 확인한 적 없으므로 정상적인 작동을 보장하지 못 함 |
| `dotNET 3.1` | [Download](https://dotnet.microsoft.com/en-us/download/dotnet/3.1) | 필수     | ◼ Audio 파일 또는 Video 파일을 변환할 때 사용                                                  |
| `K-Lite Codec Pack 18.3.0 (Mega)`    | [Download](https://codecguide.com/download_k-lite_codec_pack_mega.htm) | 선택     | ◼ Audio 및 Video 코덱 설치<BR>◼ 추출 된 Audio 파일 또는 Video 파일이 정상적으로 재생되지 않을 때 설치<BR>◼ 18.3.0 버전이 아니어도 됨 |

<BR><BR><BR>

## ❗ 주의 사항 ❗
### ※ 모든 내용은 2024-05-25 AM 05:07 기준이며, 작업 시점, 방법에 따라 총 용량 및 파일 개수가 달라집니다.
### ※ 반드시 저장 장치의 여유 공간을 확인 후 작업하시기 바랍니다.
### ※ 발견 된 문제를 미리 확인하여 작업 중 적절히 대처할 수 있도록 준비하십시오.

<details>
  <summary>📛 지금까지 발견 된 문제(* 발견시 추가 예정)</summary><BR>


`발견시 추가 예정`<BR>
발견시 추가 예정

<BR>

</details>

<BR>

**클라이언트 또는 manifest.db에서 가르키는 각 폴더별 명칭은 아래 목록을 클릭하여 참고하십시오.** <BR>
<details>
  <summary>🗂 각 폴더별 이름</summary><BR>

```
\a = Asset
\b = BGM
\s = SE(Sound Effect)
\v = Voice
\t = Temp
```

</details>

<BR>

**각 manifest의 구조는 아래 목록을 클릭하여 참고하십시오.** <BR>
<details>
  <summary>🧾 All Manifests (Level 2)</summary><BR>

※ 원본 국가, 작업하는 시점 또는 방법에 따라 일부 다르게 표기될 수 있음

```
📁 Priconne_Extractor
  ├📁 a
  │  ├📁 all
  │  ├📁 animation
  │  ├📁 arcade
  │  ├📁 banner
  │  ├📁 bg
  │  ├📁 caravan
  │  ├📁 clanbattle
  │  ├📁 colosseum
  │  ├📁 comic
  │  ├📁 consttext
  │  ├📁 dailytask
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
  │  ├📁 talentquest
  │  ├📁 travel
  │  ├📁 unit
  │  └📁 wac
  ├📁 assets
  ├📁 b
  ├📁 m
  │  └📁 t
  ├📁 manifest
  ├📁 s
  └📁 v
     └📁 t
```

</details>

<BR><BR><BR>

## ⏩ 사용 방법
01. zip 파일 다운로드 후 적절한 위치에 압축 해제 합니다. <BR>
![2024-03-23 21 07 06](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/d8c0bd93-36fe-44be-afe1-e6b814415a52) <BR><BR><BR>



2. `01_Install` 폴더로 이동 후 본문 상단 `💾 다운로드`을 참고하여 파일을 설치합니다. <BR>
![2024-03-23 21 07 37](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/d3ebf8ce-080e-49c0-9f6b-3ebb3444e335) <BR>
![2024-03-23 21 10 09](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/c7556e8e-76d8-4fe3-b074-3d26fa43425a) <BR>
**[ ※ 주의 ] Add python.exe to PATH 에 반드시 체크 후 Install Now 클릭** <BR>
(📌 미처 누르지 못했다면 설치파일을 다시 실행 또는 소프트웨어 제거 후 재 설치) <BR><BR><BR>



3. 모두 설치가 끝났다면 `02_Tools` 폴더로 이동합니다. <BR>
![2024-03-23 21 11 06](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/3ab44e7f-c5fb-473e-895b-db47198eb569) <BR><BR><BR>



4. `00. Install required Python packages.bat` 파일을 실행하여 Python Package를 설치합니다. <BR>
![2024-03-23 21 12 30](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/2f38827c-7cee-4b4a-9366-f1b56ca6d95f) <BR>
![2024-03-23 21 12 42](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/c223c840-cf1d-4abf-b5d6-3d295be3c43d) <BR>
![2024-03-23 21 12 58](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/44477a1c-76e8-45a1-a494-3ac7b4b595c2) <BR>
(📌 필요 Python Package 설치가 끝나면 위와 같은 화면이 표기됩니다.) <BR><BR><BR>



6. `01. Manifest File Renamer` 파일을 실행하여 z <BR>
![2024-03-23 21 13 09](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/513b5cfc-62f1-4060-9060-7e8eeed8aeb2) <BR>
![2024-03-23 21 13 25](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/83372f25-6c7e-4572-a2e1-ca001935adda) <BR>
(📌 manifest 추출이 끝나면 위와 같이 파일이 생깁니다.) <BR><BR><BR>



7. `02_Priconne_Original_Resource_Download_to_Convert.py` 파일을 실행하여 다운로드 및 변환 할 manifest 정보를 입력하고 Enter키를 누릅니다. <BR>
![2024-03-23 21 13 40](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/657ac134-e740-4914-9094-bfe64fd1dfab) <BR>
![2024-03-23 21 13 58](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/3e2b1fce-0ba5-4152-bc4e-ead27f5030ba) <BR><BR>

**[ 🛑 경고 🛑 ] 반드시 저장 공간이 여유로운 곳에서 작업하십시오.** <BR><BR><BR>
 
![_2024_03_23_21_15_29_34-ezgif com-video-to-gif-converter](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/025f37d3-648f-470f-83ad-e6ecf3f67755) <BR>
(📌 `banner2_assetmanifest` 입력 결과) <BR><BR><BR>

![2024-03-23 21 34 48](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/c1cd31f9-8e3b-4d40-96b1-26c9546f8d05) <BR>
**만약 위 사진처럼 예상치 못한 오류로 인해 작업이 중단 또는 멈춘다면 창을 닫고 다시 열어 다시 작업 해 주시기 바랍니다.** <BR><BR><BR>

![2024-03-23 21 15 49](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/a5c05a23-1043-40a5-a754-ccbb35861f11) <BR>
![2024-03-23 21 15 58](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/36d200ae-b3d2-46dc-b1bf-a613e4caa1ba) <BR>
(📌 `banner2_assetmanifest` 입력 결과) <BR><BR>

![2024-03-30 02 06 07](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS/assets/99892351/edae366b-51c7-4b14-b0dc-517a204c05ea) <BR>
(📌 `movie2manifest` 입력 결과) <BR><BR>

작업이 성공적으로 끝나면 새로운 폴더와 함께 원본 파일 및 변환 된 파일을 확인할 수 있습니다.

<BR><BR><BR>

## 선택 작업
**아래 작업은 필수 작업은 아니며, 필요에 따라 사용하시면 됩니다.** <BR><BR>

**[선택 작업]** <BR>
캐릭터 명을 모두 추출하고 싶다면 `05. Character List Export.py` 파일을 실행합니다. <BR><BR>
![2024-03-23 21 17 06](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/218c4b3d-c335-49fb-8189-f66cea4085cd) <BR>
![_2024_03_23_21_45_30_866-ezgif com-video-to-gif-converter](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/2914305b-b991-4b95-9c42-0e72141c17ad)

<BR><BR><BR>

**[선택 작업]** <BR>
입력 한 캐릭터명 전체 또는 일부를 기준으로 대사 정보 및 Audio 파일 정보를 찾고싶다면 `06. Vocal Resource Info Export.py` 파일을 실행합니다. <BR><BR>
![2024-03-23 21 49 57](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/0ac69fab-c8b0-4316-8d75-d0120dd4b772) <BR>
![SHANA_2024_03_23_21_50_37_194-ezgif com-video-to-gif-converter](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/a9da55db-3b00-441e-848d-17378091521c) <BR>

예를 들어, 'コッコロ(=콧코로)'를 입력하지 않고, 'コ'만 입력 후 검색을 하면 모든 캐릭터 이름 중 'コ'가 포함 된 캐릭터 모두 결과값을 반환합니다. <BR>
(📌 위 GIF에 녹화 된 내용 기준으로 'コッコロ(콧코로)', 'ペコリーヌ(=페코린느)', 'マコト(=마코토)', 'ミヤコ(=미야코)' 가 포함 된 결과가 출력 된 것을 확인할 수 있습니다.)

<BR><BR><BR>

**[선택 작업]** <BR>
원본 Resource 파일을 모두 제거하려는 경우 `07. Original Resource Remover.py` 파일을 실행하여 원본 Resource 파일을 제거합니다. <BR><BR>
![2024-03-23 21 16 09](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/23a983ed-5d14-445e-8b22-ff94c48fdffc) <BR>
![_2024_03_23_21_40_55_699-ezgif com-video-to-gif-converter](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/138d888e-9da5-41ed-9871-ba3dd0ab1cf5)

<BR><BR><BR>

## ⚙ 고급 설정 (선택)
### ※ 이 작업은 Python 언어로 작성 된 Script의 내용을 이해하고 응용할 수 있는 분들께 추천드리는 작업입니다. <BR><BR>

### ❗ 필수 작업 ❗ <BR>
![2024-03-30 02 18 44](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS/assets/99892351/935aef2e-f653-448e-8c0d-8c1a7d8fb5c0) <BR>
`파일 -> 옵션 -> 보기 -> 숨김 파일 및 폴더`상태를 `숨김 파일, 폴더 및 드라이브 표시`로 변경 후 확인 <BR><BR>

![2024-03-30 02 23 35](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS/assets/99892351/020ff6da-1dcd-4b5a-834a-abaabd2e2c70) <BR>
수정하고자 하는 파일 선택 후 `마우스 우클릭 -> 속성 -> 일반 -> 특성`항목 중 `읽기 전용(R)`상태 해제 후 확인 <BR><BR>

**위 작업을 모두 끝낸 후 작업하시기 바랍니다.**

<BR>



<details>
  <summary>🛠 *.usm 파일을 *.mp4 파일이 아닌 다른 확장자로 변환하고자 하는 경우?</summary><BR>

`PRICONNE_EXTRACTION_TOOLS`에 포함 된 `UsmToolkit`은 FFmpeg 표준 구문을 사용합니다.<BR><BR>

01. `\Priconne_Extractor\src\files`로 이동 후 `movie_file.py`파일 내용 중 `extract_path`부분 수정 <BR>
02. `\Priconne_Extractor\usmtoolkit`로 이동 후 `config.json`파일 내용 중 `OutputFormat`부분 수정<BR><BR>
```
    # 만약, *.mp4 파일이 아닌 *.mkv 파일로 저장하고 싶다면?

    # ▼ movie_file.py 파일 내용 중 일부 ▼
    def extract(self) -> None:
        self.download()
        extract_path = self.path.parent.parent / (self.path.stem + ".mkv")  # <--- 확장자 수정
        if extract_path.exists():
            return

    # ▼ config.json 파일 내용 ▼
{
    "VideoParameter" : "-c:v copy",
    "AudioParameter" : "-c:a ac3 -b:a 640k -af pan='stereo|FL=FL+FC+0.5*BL+BR|FR=FR+LFE+0.5*BL+BR'",
    "OutputFormat" : "mkv"
}
    # ▲ OutputFormat을 mkv로 수정 ▲
```

<BR>

**보다 자세한 설정은 FFmpeg 표준 구문을 확인하시기 바랍니다.** <BR>
[📚 FFmpeg 표준 구문 보러 가기](https://ffmpeg.org/ffmpeg-codecs.html)

</details>

<BR><BR><BR>

## 해야 할 일
- 게임 출석
- 콧코로 수첩
- 지역
- 이벤트 스토리
- 던전
- 아레나, 프레나
- 클랜전

<BR><BR><BR>

## Special Thanks to
✨ Princess Connect! Re:Dive Game Users <BR>
