# 다락방 (Darackbang)

로스트아크 전용 Discord 파티 모집 봇 MVP입니다.

## 현재 기능
- `/모집패널`로 모집 패널 생성
- 레이드 / 난이도 / 숙련도 / 최소 아이템 레벨 / 출발시간 / 인원 / 메모 입력
- 딜러 / 서폿 참여
- 참여 취소
- 인원 자동 갱신
- 정원 충족 시 자동 마감
- 공대장/관리자 수동 마감
- 모집 생성 시 전용 스레드 생성
- SQLite 영속 저장
- 봇 재시작 후 열린 모집 버튼 복구

## 실행
```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

`.env`에 `DISCORD_TOKEN`을 입력하세요. 빠른 슬래시 명령어 동기화를 원하면 `GUILD_ID`도 입력합니다.

## 모집 입력 예시
마지막 입력란:
`21:00 | 딜6 서폿2 | 숙제팟, 듣코 가능`

## 다음 단계
- 레이드/난이도/숙련도 Select UI
- 모집 수정/재오픈/삭제
- 캐릭터 프로필 및 로스트아크 API 연동
- PostgreSQL 전환 및 Railway 배포
