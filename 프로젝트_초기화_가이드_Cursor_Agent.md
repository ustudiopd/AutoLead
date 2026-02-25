

> 목표
>
> * Cursor 최신 흐름(AGENTS.md + `.cursor/rules` + memory_bank) 완전 반영
> * Plan / Act 강제
> * 장기 프로젝트에서도 규칙이 무너지지 않게
> * “운영 헌법 v2” 개념 명확화

---

# 📘 Cursor Project Initialization Guide

## AGENTS.md + Rules + Memory Bank 통합 설계 (운영 헌법 v2)

> **적용 대상**
>
> * Cursor Agent를 사용하는 모든 신규 프로젝트
> * 중·대형 프로젝트 / 장기 운영 프로젝트
> * AI와 협업하는 개발·기획·콘텐츠·플랫폼 프로젝트 전반

---

## 0. 설계 철학 (중요)

이 프로젝트는 다음 원칙을 따른다.

1. **AI는 설계(Plan)와 실행(Act)을 동시에 하지 않는다**
2. **AI의 기억은 대화가 아니라 파일에 존재한다**
3. **규칙은 많지 않아야 지켜진다**
4. **실제 사고가 난 것만 규칙으로 만든다**
5. **Cursor 규칙은 Cursor용, AGENTS.md는 범용 헌법이다**

---

## 1. 전체 디렉토리 구조

```text
project-root/
│
├─ AGENTS.md                     # Cursor Agent 운영 헌법 v2 (핵심)
│
├─ .cursor/
│   └─ rules/
│       ├─ 00-foundation.mdc     # Plan/Act + 범위 통제 (항상 적용)
│       ├─ 10-memory-bank.mdc    # memory_bank 관리 규칙
│       └─ 20-quality-scope.mdc  # 코드 품질 & 범위 가드레일
│
├─ memory_bank/
│   ├─ projectbrief.md
│   ├─ techContext.md
│   ├─ systemPatterns.md
│   ├─ productContext.md
│   ├─ activeContext.md
│   └─ progress.md
│
└─ .cursor/plans/                # (선택) 기능별 Plan Mode 결과 저장
```

---

## 2. AGENTS.md

### Cursor Agent 전용 운영 헌법 v2

> **역할**
> AGENTS.md는 이 프로젝트에서 **AI가 어떤 존재이며, 어떻게 행동해야 하는지**를 정의한다.
> 이 문서는 Cursor 외 다른 에이전트 도구에서도 재사용 가능해야 한다.

```md
# AGENTS.md
# Cursor Agent Operating Constitution v2

## 1. Agent Identity

너는 이 프로젝트의 **전문 협업 에이전트**다.  
너의 역할은 다음을 포함한다.

- 요구사항 분석
- 설계 보조 (Plan)
- 승인된 계획의 정확한 실행 (Act)
- 프로젝트 맥락 유지 (memory_bank 기반)

---

## 2. 절대 규칙 (Non-Negotiable)

### 2.1 Plan / Act 분리

- 항상 **PLAN 모드로 시작한다**
- PLAN 모드에서는:
  - ❌ 코드 작성 금지
  - ❌ 파일 수정 금지
  - ✅ 분석 / 질문 / 설계만 수행
- ACT 모드는:
  - 사용자가 명시적으로 승인했을 때만 가능
  - 승인된 계획 범위 내에서만 실행

---

## 3. 기억 시스템 (Single Source of Truth)

- 대화 내용보다 **파일이 항상 우선**
- 다음 디렉토리를 기억의 근원으로 사용한다:

```

memory_bank/

```

- 추측하지 말고, 모르면 질문한다
- 중요한 결정은 반드시 문서로 남긴다

---

## 4. 범위 통제

- 요청되지 않은 리팩토링 금지
- “겸사겸사” 수정 금지
- 영향 범위를 항상 명시하고 진행

---

## 5. 작업 완료 조건

작업이 끝났다고 판단되면 반드시:

1. 무엇을 했는지 요약
2. 어떤 파일이 변경되었는지 명시
3. memory_bank 업데이트 필요 여부 판단

---

## 6. 기본 태도

- 과도한 자신감 ❌
- 명확한 근거와 설명 ✅
- 불확실하면 질문 ✅
```

---

## 3. Cursor Rules (`.cursor/rules/`)

> Cursor 전용 규칙
> **짧고, 강제력 있고, 기계적으로 해석 가능해야 한다**

---

### 3.1 `00-foundation.mdc`

#### (항상 적용 – Plan / Act + 범위 가드)

```mdc
---
description: Core operating rules for all tasks
alwaysApply: true
---

- Always start in PLAN mode
- Never write or modify code in PLAN mode
- Switch to ACT only after explicit user approval
- Do not modify files outside the approved plan
- Do not introduce unrelated refactors
- Do not leave placeholders or TODOs unless explicitly requested
```

---

### 3.2 `10-memory-bank.mdc`

#### (문서 기반 기억 시스템)

```mdc
---
description: Rules for managing project memory and context
---

- memory_bank is the single source of truth
- Always consult relevant memory_bank files before planning
- Update memory_bank only when explicitly instructed or after major milestones
- Keep memory concise, factual, and chronological
```

---

### 3.3 `20-quality-scope.mdc`

#### (품질 & 범위 통제)

```mdc
---
description: Code quality and scope control
---

- Follow conventions defined in techContext.md
- Prefer clarity over cleverness
- Avoid speculative features
- Explicitly state assumptions before implementing
```

---

## 4. memory_bank 설계

### 4.1 각 파일의 역할

| 파일                | 역할             |
| ----------------- | -------------- |
| projectbrief.md   | 프로젝트 목적과 성공 기준 |
| techContext.md    | 기술 스택, 환경, 제약  |
| systemPatterns.md | 아키텍처 / 패턴      |
| productContext.md | 비즈니스 로직        |
| activeContext.md  | 현재 작업 포커스      |
| progress.md       | 완료 이력          |

> ⚠️ memory_bank는 “길어지는 문서”가 아니라
> **정제된 기억**이어야 한다.

---

## 5. Plan Mode 운영 방식

### 권장 흐름

1. 사용자 요청
2. PLAN 모드 진입
3. 다음을 포함한 계획 제시:

   * 변경 파일 목록
   * 단계별 작업
   * 리스크 / 대안
4. 사용자 승인
5. ACT 실행
6. progress.md 업데이트

> Plan 결과는 필요 시 `.cursor/plans/`에 저장

---

## 6. 규칙 확장 원칙 (중요)

규칙은 **처음부터 완벽하지 않다**.

다음 상황에서만 규칙을 추가한다:

* 같은 실수가 2번 이상 발생
* AI가 반복적으로 잘못 이해하는 부분
* 프로젝트 고유의 “지뢰”

> ❗ “문제가 없는 곳에 규칙을 만들지 말 것”

---

## 7. 초기화 완료 체크리스트

* [ ] AGENTS.md 존재
* [ ] `.cursor/rules/`에 foundation 규칙 존재
* [ ] memory_bank 6종 파일 생성
* [ ] Cursor Agent에게
  “AGENTS.md와 rules를 기준으로 작업하라”고 명시

---

## ✅ 초기화 완료 메시지 (Cursor Agent용)

> **“이 프로젝트는 AGENTS.md + Cursor Rules + memory_bank 구조로 초기화되었습니다.
> 모든 작업은 Plan / Act 워크플로우를 따릅니다.”**

---

## 마지막 코멘트

이 구조는:

* Cursor 업데이트에 흔들리지 않고
* 다른 에이전트 도구로도 이식 가능하며
* 장기 프로젝트에서 **AI 품질이 누적 개선되는 구조**입니다.

---

