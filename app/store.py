"""6단계 — 저장소. 라우터는 이 파일의 PLANS 만 안다.
"""
# 지금은 메모리. 2일차 이후 SQLite로 바꿔도 라우터는 그대로 둔다.
PLANS: dict[int, dict] = {}
