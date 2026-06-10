# Facet Schema — 추천 시스템용 Content Understanding Profile

영화/시리즈의 줄거리 + 전문가 감상평 + 일반 감상평을 조합해 생성하는 구조화 facet.
mediaX 통제어휘 로직을 이식하되 **추천 우선순위 + 타입 체계**로 재설계.

## 타입 체계 (핵심)

같은 facet이라도 추천에서 쓰임이 다르다:

| 타입 | 용도 | 검증 |
|------|------|------|
| `score` 0~1 | 랭킹/필터 축 | clamp(0,1), 실패 시 None |
| `enum` 단일 | 라우팅/분기 | 통제어휘 외 → None |
| `vocab list` 다중 | 매칭 (Jaccard) | 통제어휘 외 제거 |
| `free list` | 롱테일 태그 | 정규화(trim/cap) |
| `text` | 설명 | trim + 길이 제한 |

## 1순위 (MVP) — 구현 완료

| 영역 | 항목 | 타입 |
|------|------|------|
| 장르 | `primary_genre` | enum |
| | `sub_genre` | vocab list |
| | `micro_genre` | free list |
| 줄거리 | `premise` | text |
| | `conflict` | enum (내적/대인/사회/생존/도덕/운명) |
| | `theme` | vocab list |
| | `ending_type` | enum (해피/새드/열린/반전/비극/잔잔) |
| 감정 | `mood` | vocab list |
| | `tension` | score |
| | `emotional_aftertaste` | vocab list (여운/먹먹/통쾌/씁쓸/…) |
| 리뷰 반응 | `immersion` | score |
| | `boredom_risk` | score |
| | `pacing_reaction` | enum (느리다/적절/빠르다) |
| | `ending_reaction` | enum (만족/호불호/실망/충격) |
| | `rewatch_value` ★ | score |
| 시청 상황 | `attention_required` | score |
| | `emotional_energy_required` | score |
| 안전/회피 | `violence` / `gore` / `sexual_content` / `spoiler_sensitivity` | score |
| 종합 | `sentiment_score` | score |
| | `one_liner` | text |

★ = 보완 추가 (제안 항목 외)

## 보완 (채택)

### safety_flags — hard-filter용 파생
안전 score 임계(0.5) 초과 시 boolean + age 파생. 추천 "회피" 필터 고속화.
```json
"safety_flags": {
  "is_violent": true, "is_gory": false, "is_sexual": false,
  "age_suggestion": "15세이상관람가"
}
```
age 경계: peak≥0.8 청불 / ≥0.5 15세 / ≥0.3 12세 / else 전체.

### _coverage + confidence — 신뢰도 신호
**원본 폐기 원칙**상 facet이 몇 개 소스에 근거했는지가 신뢰도의 유일한 신호.
저신뢰 facet으로 추천 매칭 시 품질 저하 → confidence로 가중치 조절.
```json
"_coverage": {"source_count": 6, "by_type": {...}, "has_expert": true, "has_user": true},
"confidence": 1.0
```
휴리스틱: `min(1, n/6)*0.8 + (expert?0.1) + (user?0.1)`.

## 유사도 (추천 매칭)
`facet_overlap_score()` — enum + list vocab을 키 prefix 토큰화해 Jaccard.
score/text/메타는 제외. (별도 score 거리 함수는 추후.)

## 후속 (2/3순위)
- **2순위**: 캐릭터(protagonist_type/moral_ambiguity/empathy_level), 연출(visual_style/pacing_style/music_usage),
  전문가평(artistic_value/originality/thematic_depth), critic_audience_gap(−1~+1)/divisiveness.
- **3순위**: taste_cluster(※ per-movie 추출 아님 — facet 군집화로 **계산**되는 downstream),
  comparable_titles(환각 위험 → 미검증 플래그), mood_arc(구간별 감정 시퀀스, 구조화),
  시리즈 전용(bingeability/season_consistency/finale_satisfaction).
