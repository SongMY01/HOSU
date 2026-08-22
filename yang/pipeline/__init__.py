"""HOSU Heat Copilot 데이터 파이프라인.

임포트 시 프로젝트 루트의 `.env`를 읽어 `os.environ`에 채운다. 서비스키를 쓰는 모듈
(`geo.py`, 앞으로 붙을 `sources/*.py`)과 `mcp_server.py`가 전부 이 패키지를 거치므로
여기가 키 로딩의 단일 지점이다.

- `.env`가 없으면 조용히 넘어간다(no-op) — 아직 키가 없어도 임포트가 깨지지 않는다.
- 실제 환경변수가 `.env`보다 우선한다(dotenv 기본 동작). CI나 셸에서 넘긴 값이 이긴다.
- 경로를 프로젝트 루트로 고정했으므로 어느 디렉토리에서 실행하든 같은 파일을 읽는다.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
