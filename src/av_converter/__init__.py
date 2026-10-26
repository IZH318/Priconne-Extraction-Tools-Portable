"""오디오 및 비디오 파일 변환 패키지(AV Converter).

CRI Sofdec (.usm) 비디오를 MP4(H.264/AAC)로 디먹싱/인코딩하고,
CRI Atom (.awb, .acb, .hca) 컨테이너 내의 다중 오디오 스트림을 고음질 WAV 파일로
일괄 추출/변환하는 통합 GUI 및 오케스트레이션 엔진 제공.
"""

from .gui import AVConverterApp

__all__ = ["AVConverterApp"]

