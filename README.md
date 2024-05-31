# 프린세스 커넥트! Re:Dive Resource 추출 도구
게임 '프린세스 커넥트! Re:Dive'의 클라이언트 파일을 오프라인 환경에서 국가 상관 없이 Resource를 추출 및 변환하는 도구입니다. <BR>
(* 미처 발견하지 못한 오류가 있을 수 있습니다.)

<BR><BR><BR>



## 🔍 주요 기능
■ 클라이언트 파일이 있는 위치에서 스크립트를 실행하면 각 파일 이름을 원본 이름으로 변경 후 파일이 추출됩니다. <BR>
(* 확장자 별 변환 과정은 다음과 같습니다.)
  - *.unity3d -> *.png, *.txt
  - *.awb, *.acb -> *.wav
  - *.usm -> *.mp4
  - *storydata.bytes -> *.json
  - *storydata_storydata.bytes -> *.*

<BR><BR><BR>



## 💾 다운로드
[![icon_item_91001](https://github.com/IZH318/priconne-asset-extractor/assets/99892351/89c074f2-f869-4377-8e10-fc6a1d7e5de4)](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/releases)
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
### ※ 모든 내용은 2024-05-29 JP, KR 서버 업데이트 기준이며, 작업 시점 또는 방법에 따라 총 용량 및 파일 개수가 달라집니다.
### ※ 반드시 저장 장치의 여유 공간을 확인 후 작업하시기 바랍니다.
### ※ 발견 된 문제를 미리 확인하여 작업 중 적절히 대처할 수 있도록 준비하십시오.

<details>
  <summary>📛 지금까지 발견 된 문제</summary><BR>


`01. 한국 서버 클라이언트 일부 *.usm 파일 소리 깨짐`<BR>
`\m\t` 폴더에 있는 *.usm 파일 중 일부 *.usm 파일이 정상적으로 변환되지 않음

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
![2024-05-31 20 47 50](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/cfbdcf6f-51b8-451f-b671-95482ebf9036) <BR><BR><BR>



2. `01_Install` 폴더로 이동 후 본문 상단 `💾 다운로드`을 참고하여 파일을 설치합니다. <BR>
![2024-05-31 20 53 59](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/0941493c-3d3d-4964-862d-4a21dc6cb768) <BR>
![2024-05-31 20 48 52](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/eb56167a-9aa0-40b8-8dd0-80357f9aae92) <BR>
**[ ※ 주의 ] Python 설치 시 Add python.exe to PATH 에 반드시 체크 후 Install Now 클릭** <BR>
(📌 미처 누르지 못했다면 설치파일을 다시 실행 또는 소프트웨어 제거 후 재 설치) <BR><BR><BR>



3. 모두 설치가 끝났다면 `02_Tools` 폴더로 이동합니다. <BR>
![2024-05-31 20 55 06](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/cc8225d5-65a8-4990-8529-b56a17468d83) <BR><BR><BR>



4. `00. Install required Python packages.bat` 파일을 실행하여 Python Package를 설치합니다. <BR>
![2024-05-31 20 50 43](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/5fe76b28-4bb5-4a86-9953-8e0dc91f55b9) <BR>
![녹화_2024_05_31_17_38_16_882 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/decb8bb1-f0c8-4835-8420-e9e39c09b2b7) <BR>
![녹화_2024_05_31_17_38_16_882 mp4_snapshot_00 11 697](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/6bb9696e-52a6-42bb-9389-9872c38c257b) <BR>
(📌 필수 Python Package 설치가 끝나면 위와 같은 화면이 표시됩니다.) <BR><BR><BR>



5. 게임 클라이언트 원본 구조를 그대로 유지한 상태로 스크립트가 있는 경로로 불러옵니다. <BR>
![2024-05-31 21 00 58](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/05fe810b-1273-447a-b31e-5d2250b758b3) <BR><BR><BR>



6. `01. Manifest File Renamer.py` 파일을 실행하여 SHA1 Hash로 저장 된 파일 이름을 변경합니다. <BR>
![2024-05-31 21 02 05](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/677400d6-2c57-46e5-b235-3c9dc25e6817) <BR>

![녹화_2024_05_31_21_06_50_102 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/f232bf41-85ff-4352-ba32-af4c0907c695) <BR>

![ezgif-6-3dc6ee929c](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/a053907f-6979-4806-a488-d7706425407f) <BR>

![녹화_2024_05_31_21_06_50_102 mp4_snapshot_00 01 282](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/ca0a94af-f572-45a8-8934-8c8c4eeb1514) <BR>
(📌 파일 이름이 모두 변경되면 위와 같은 화면이 표시됩니다.) <BR><BR><BR>



7. `02. unity3d File Converter.py` 파일을 실행하여 *.unity3d 파일에서 Asset을 추출(변환)합니다. <BR>
![2024-05-31 21 12 57](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/4c9d07e1-1742-4b7b-98a9-fa4b42c8e73f) <BR>

![녹화_2024_05_31_20_20_40_361 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/db40c687-b9ce-47f6-b76f-1e2981b2c7e1) <BR>

**[ 🛑 경고 🛑 ] 반드시 저장 공간이 여유로운 곳에서 작업하십시오.** <BR><BR>

![ezgif-4-d611beffd8](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/e2c76417-ebdf-426b-b469-a5dee82cb669) <BR>

![녹화_2024_05_31_20_20_40_361 mp4_snapshot_00 01 294](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/0f3ec38f-028a-4116-b1f9-2f09849eb054) <BR>
(📌 작업이 성공적으로 끝나면 위와 같은 화면이 표시됩니다.) <BR><BR>

![2024-05-31 21 15 56](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/d1c9438c-9041-4cda-ac9b-100d83e0a487) <BR>
(📌 `\a\_Convert` 폴더) <BR><BR>

작업이 성공적으로 끝나면 원본 Resource 폴더 내 `_Convert` 폴더가 생성되며, 해당 내부에 원본 *.unity3d 파일 이름으로 추출(변환) 된 Asset이 저장되어 있는 것을 확인할 수 있습니다. <BR><BR><BR>



8. `03. Audio File Converter.py` 파일을 실행하여 *.acb, *.awb 파일에서 Resource를 추출(변환)합니다. <BR>
![2024-05-31 21 22 58](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/4cb398ea-d2d0-4984-ac83-8a51a6b51cd6) <BR>

![녹화_2024_05_31_20_26_39_551 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/e81762eb-3af8-4b86-974d-1e5ff84b0e86) <BR>

**[ 🛑 경고 🛑 ] 반드시 저장 공간이 여유로운 곳에서 작업하십시오.** <BR><BR>

![ezgif-4-575f84a008](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/3820ad83-fd3d-4230-b038-79fa6c81c287) <BR>

![녹화_2024_05_31_20_26_39_551 mp4_snapshot_00 07 285](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/41f5457a-7144-4e52-bd80-44fd3976c1cf) <BR>
(📌 작업이 성공적으로 끝나면 위와 같은 화면이 표시됩니다.) <BR><BR>

![2024-05-31 21 23 46](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/eb12e53a-4bec-4e65-a6cc-d7703a67c479) <BR>
(📌 `\b\_Convert` 폴더) <BR><BR>

작업이 성공적으로 끝나면 원본 Resource 폴더 내 `_Convert` 폴더가 생성되며, 해당 폴더 내부에 원본 *.acb 파일 이름 또는 *.awb 파일 이름으로 추출(변환) 된 Resource가 저장되어 있는 것을 확인할 수 있습니다. <BR><BR><BR>



9. `04. Video File Converter.py` 파일을 실행하여 *.usm 파일에서 Resource를 추출(변환)합니다. <BR>
![2024-05-31 21 25 04](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/841748fe-f346-44eb-8857-b2c2641056ff) <BR>

![녹화_2024_05_31_20_26_57_870 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/8c64043f-af90-45dd-a0df-c93698c72d4e) <BR>

**[ 🛑 경고 🛑 ] 반드시 저장 공간이 여유로운 곳에서 작업하십시오.** <BR><BR>

![ezgif-4-37e0380221](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/98854e82-e073-4c55-8936-130a02186318) <BR>

![녹화_2024_05_31_20_26_57_870 mp4_snapshot_00 02 951](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/cd142076-b903-4a24-a33d-f322197d39fa) <BR>
(📌 작업이 성공적으로 끝나면 위와 같은 화면이 표시됩니다.) <BR><BR>

![2024-05-31 21 28 45](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/18675838-dd2b-4a0f-a5dc-30d3cc385eea) <BR>
(📌 `\m\_Convert` 폴더) <BR><BR>

작업이 성공적으로 끝나면 원본 Resource 폴더 내 `_Convert` 폴더가 생성되며, 해당 폴더 내부에 원본 *.usm 파일 이름으로 추출(변환) 된 Resource가 저장되어 있는 것을 확인할 수 있습니다.



<BR><BR><BR>

## 선택 작업
**아래 작업은 필수 작업은 아니며, 필요에 따라 사용하시면 됩니다.** <BR><BR>

**[선택 작업]** <BR>
캐릭터 명을 모두 추출하고 싶다면 `05. Character List Export.py` 파일을 실행합니다. <BR><BR>
![녹화_2024_05_31_20_34_50_160 mp4_snapshot_00 00 000](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/066c93b1-5395-470a-9478-e65e0b6f7f07) <BR>

![ezgif-5-fbc7712a65](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/70735b26-c6c5-47c4-a7d7-6f5d0ca0f25a)

<BR><BR><BR>



**[선택 작업]** <BR>
입력 한 캐릭터명 전체 또는 일부를 기준으로 대사 정보 및 Audio 파일 정보를 찾고싶다면 `06. Vocal Resource Info Export.py` 파일을 실행합니다. <BR><BR>
![캡처_2024_05_31_21_53_33_344](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/0c190cf7-6d68-4967-9a0f-1e928fe35538) <BR>

![ezgif-6-c9bead1666](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/dd55be38-851c-4400-a665-bcc946c43db4) <BR>

예를 들어, 'コッコロ(=콧코로)'를 입력하지 않고, 'コ'만 입력 후 검색을 하면 모든 캐릭터 이름 중 'コ'가 포함 된 캐릭터 모두 결과값을 반환합니다. <BR>
(📌 위 GIF에 녹화 된 내용 기준으로 'コッコロ(콧코로)', 'ペコリーヌ(=페코린느)', 'マコト(=마코토)', 'ミヤコ(=미야코)' 등 'コ'가 포함 된 결과가 출력 된 것을 확인할 수 있습니다.)

<BR><BR><BR>



**[선택 작업]** <BR>
원본 Resource 파일을 모두 제거하려는 경우 `07. Original Resource Remover.bat` 파일을 실행하여 원본 Resource 파일을 제거합니다. <BR><BR>
![녹화_2024_05_31_20_43_14_736 mp4_snapshot_00 00 263](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/81051272-7a83-4669-b01b-0b46f23747ac) <BR>
![ezgif-6-5b02b54d9b](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/4fc88979-1fdd-4385-bf3e-876d0a022821)



<BR><BR><BR>



## ⚙ 고급 설정 (선택)
### ※ 이 작업은 Python 언어로 작성 된 Script의 내용을 이해하고 응용할 수 있는 분들께 추천드리는 작업입니다. <BR><BR>

### ❗ 필수 작업 ❗ <BR>
![PRICONNE_EXTRACTION_TOOLS(Portable)_AIO 숨김폴더 해제 지시](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/6a58735a-0eaa-4ca0-b4a7-188d4483335b) <BR>
`파일 -> 옵션 -> 보기 -> 숨김 파일 및 폴더`상태를 `숨김 파일, 폴더 및 드라이브 표시`로 변경 후 확인 <BR><BR>

![PRICONNE_EXTRACTION_TOOLS(Portable)_AIO 읽기전용 해제 지시](https://github.com/IZH318/PRICONNE_EXTRACTION_TOOLS_Portable/assets/99892351/33179bbf-4e0d-4624-9b1d-4e313879d2bb) <BR>
수정하고자 하는 파일 선택 후 `마우스 우클릭 -> 속성 -> 일반 -> 특성`항목 중 `읽기 전용(R)`상태 해제 후 확인 <BR><BR>

**위 작업을 모두 끝낸 후 작업하시기 바랍니다.**

<BR>



<details>
  <summary>🛠 *.usm 파일을 *.mp4 파일이 아닌 다른 확장자로 변환하고자 하는 경우?</summary><BR>

`PRICONNE_EXTRACTION_TOOLS(Portable)_AIO`에 포함 된 `UsmToolkit`은 FFmpeg 표준 구문을 사용합니다.<BR><BR>

01. `\04. Video File Converter.py`코드 중 `extract_path = output_folder_path / (usm_file.stem + ".mp4")` 부분에서 `.mp4` 수정 <BR>
02. `\02_Tools\usmtoolkit`로 이동 후 `config.json`파일 내용 중 `OutputFormat`부분 수정 <BR><BR>
```
    # 만약, *.mp4 파일이 아닌 *.mkv 파일로 저장하고 싶다면?

    # ▼ 04. Video File Converter.py 파일 내용 중 일부 ▼
    # 변환할 *.mp4 파일 경로 생성
    extract_path = output_folder_path / (usm_file.stem + ".mp4")  # <--- 확장자 수정

    # ▼ config.json 파일 내용 ▼
{
    "VideoParameter" : "-c:v copy",
    "AudioParameter" : "-c:a ac3",
    "OutputFormat" : "mkv"  # <--- 확장자 수정
}
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
