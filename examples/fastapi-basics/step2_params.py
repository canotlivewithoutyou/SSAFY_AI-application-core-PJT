"""2단계 — 경로 파라미터와 쿼리 파라미터

실행:
    uvicorn step2_params:app --reload

해 볼 것:
    /movies/abc               먼저 결과를 예상하고 불러 본다 → 422. 함수는 실행되지 않는다
    /movies/2                 경로 파라미터 — 하나를 콕 집는다
    /movies?keyword=명량       쿼리 파라미터 — 목록을 거른다
"""
from fastapi import FastAPI

app = FastAPI()
MOVIES = {1: "기생충", 2: "명량", 3: "올빼미"}

@app.get("/movies/{movie_id}")
def get_movie(movie_id: int):
    return {"movie_id": movie_id, "title": MOVIES.get(movie_id)}

@app.get("/movies")
def list_movies(keyword: str ="", limit: int = 10):
    found = [t for t in MOVIES.values() if keyword in t]
    return {"count": len(found), "movies": found[:limit]}