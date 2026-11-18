# data/

- `synthetic/` — 센터 명세서(v12)를 따르는 **가상 데이터**. 커밋하지 않고 아래 명령으로 다시 만든다(같은 seed면 같은 결과).
  ```
  python -m jeju_agent.synth 1-08 --period 202505-202604 --out data/synthetic
  python -m jeju_agent.synth 4-11 --period 20260401-20260407 --out data/synthetic
  ```
  - 컬럼명·순서·코드값은 명세서와 같고, 수치는 가짜다. 시군구·권역 배정은 근사치다.
  - 실제 센터 CSV의 인코딩은 미확인이라 기본은 UTF-8(BOM), `--encoding cp949`로 바꿀 수 있다.
  - 'NA'는 결측이 아니라 명세서상 값이다. 읽을 때 `keep_default_na=False`.
- `raw/`, `private/` — 실제 데이터 자리(gitignore).
