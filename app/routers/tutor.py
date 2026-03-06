"""
routers/tutor.py  ─  튜터 기능 API 라우터

담당 엔드포인트:
    GET  /api/units                → 전체 단원 목록
    GET  /api/problem              → 단원별 문제 조회
    POST /api/explain              → 단원 개념 설명 생성
    POST /api/explain/evaluate     → 학생 역설명 평가
    POST /api/ask                  → 실시간 질의응답 (RAG)
    POST /api/evaluate             → 학생 답변 채점
    POST /api/history              → 학습 결과 저장
    GET  /api/history              → 학습 이력 조회 (리포트)
    GET  /api/history/incorrect    → 오답 목록 조회

"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.utils.db_manager import save_history, get_user_history, get_incorrect_problems

# ✅ 튜터 로직은 서비스 계층을 통해서만 접근
from app.services.tutor_service import (
    fetch_units,
    fetch_problem,
    get_explanation       as svc_get_explanation,      # ← 라우터 함수명 충돌 방지
    evaluate_explanation  as svc_evaluate_explanation, # ← 동일한 이유
    ask_tutor             as svc_ask_tutor,
    grade_answer          as svc_grade_answer,
    get_problem_image_b64,
)

router = APIRouter()

# ─────────────────────────────────────────────────────────
# ① 요청/응답 스키마 정의 (Pydantic)
#
# [스키마를 왜 별도로 정의하나?]
# - FastAPI가 요청 body의 타입/필드를 자동 검증
# - /docs Swagger 문서에 자동으로 표시됨
# - 없는 필드, 잘못된 타입 요청은 422 에러로 자동 차단
# ─────────────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    """POST /api/explain 요청 body"""
    unit_name: str  # 예: "분수의 덧셈과 뺄셈"


class StudentExplainRequest(BaseModel):
    """POST /api/explain/evaluate 요청 body"""
    concept: str             # 평가할 개념명
    student_explanation: str # 학생이 직접 작성한 설명


class AskRequest(BaseModel):
    """POST /api/ask 요청 body"""
    question: str               # 학생의 질문
    chat_history: list = []     # 이전 대화 기록 (없으면 빈 리스트)


class EvaluateRequest(BaseModel):
    """POST /api/evaluate 요청 body"""
    problem: dict    # curator에서 받은 문제 dict 그대로 전달
    student_answer: str


class SaveHistoryRequest(BaseModel):
    """POST /api/history 요청 body"""
    problem_id: str
    unit: str
    is_correct: bool


# ─────────────────────────────────────────────────────────
# ② GET /api/units  ─  단원 목록 조회
# ─────────────────────────────────────────────────────────
@router.get("/units")
async def get_unit_list(current_user: dict = Depends(get_current_user)):
    """
    전체 단원 목록을 반환합니다.

    [기존 main.py 코드]
        units = load_full_dataset()['단원'].unique().tolist()
        sel_unit = st.selectbox("어떤 단원을 배워볼까요?", units)

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/units", {
            headers: { "Authorization": "Bearer " + token }
        });
        const data = await res.json();
        // { "units": ["분수의 덧셈과 뺄셈", "소수의 곱셈", ...] }

        // HTML <select> 태그에 동적으로 옵션 추가
        data.units.forEach(unit => {
            const option = document.createElement("option");
            option.value = unit;
            option.text = unit;
            document.getElementById("unit-select").add(option);
        });
    """
    try:
        units = await fetch_units()
        return {"units": units}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"단원 목록 조회 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ③ GET /api/problem?unit=분수  ─  단원별 문제 조회
# ─────────────────────────────────────────────────────────
@router.get("/problem")
async def get_problem(unit: str, current_user: dict = Depends(get_current_user)):
    """
    선택한 단원에서 문제를 무작위로 1개 반환합니다.

    [Query Parameter 방식]
    URL에 ?unit=분수의덧셈 형태로 전달합니다.
    FastAPI는 함수 인자 중 Body가 아닌 것을 자동으로 Query로 처리합니다.

    [기존 main.py 코드]
        st.session_state['current_problem'] = df[df['단원'] == sel_unit].iloc[0].to_dict()

    [변경 후 HTML fetch 예시]
        const unit = document.getElementById("unit-select").value;
        const res = await fetch(
            `http://localhost:8000/api/problem?unit=${encodeURIComponent(unit)}`,
            { headers: { "Authorization": "Bearer " + token } }
        );
        const data = await res.json();
        // { "problem": { "ID": "001", "단원": "분수", "문제": "...", "풀이및정답": "..." } }

        // 문제 화면에 렌더링
        document.getElementById("problem-text").innerText = data.problem["문제"];
    """
    problem = await fetch_problem(unit)

    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{unit}' 단원의 문제를 찾을 수 없습니다."
        )

    # NaN 값이 있으면 JSON 직렬화 실패 → None으로 변환
    cleaned = {k: (None if str(v) == "nan" else v) for k, v in problem.items()}

    # 이미지 조회 (없으면 None)
    image_b64 = get_problem_image_b64(str(cleaned.get("ID", "")))

    return {"problem": cleaned, "image_b64": image_b64}


# ─────────────────────────────────────────────────────────
# ④ POST /api/explain  ─  개념 설명 생성
# ─────────────────────────────────────────────────────────
@router.post("/explain")
async def get_explanation(
    body: ExplainRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    루미 선생님이 선택한 단원의 개념을 설명합니다.

    [기존 main.py 코드]
        if 'explanation' not in st.session_state:
            st.session_state['explanation'] = explain_concept(st.session_state['selected_unit'])
        st.write(st.session_state['explanation'])

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/explain", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ unit_name: "분수의 덧셈과 뺄셈" })
        });
        const data = await res.json();
        document.getElementById("explanation-box").innerText = data.explanation;
    """
    try:
        explanation = await svc_get_explanation(body.unit_name)
        return {"explanation": explanation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"개념 설명 생성 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑤ POST /api/explain/evaluate  ─  학생 역설명 평가
# ─────────────────────────────────────────────────────────
@router.post("/explain/evaluate")
async def evaluate_student_explanation(
    body: StudentExplainRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    학생이 직접 설명한 내용을 AI가 평가하고 PASS/FAIL을 반환합니다.

    [기존 main.py 코드]
        feedback = evaluate_concept_understanding(st.session_state['selected_unit'], user_desc)
        st.session_state['is_passed'] = "[PASS]" in feedback.upper()

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/explain/evaluate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                concept: "분수의 덧셈과 뺄셈",
                student_explanation: "분모가 같으면 분자끼리 더하면 돼요"
            })
        });
        const data = await res.json();
        // { "feedback": "잘 이해했어요! ...", "is_passed": true }

        if (data.is_passed) {
            showNextStep("문제풀기");
        } else {
            showNextStep("보충설명");
        }
    """
    try:
        result = await svc_evaluate_explanation(body.concept, body.student_explanation)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이해도 평가 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑥ POST /api/ask  ─  실시간 질의응답 (RAG)
# ─────────────────────────────────────────────────────────
@router.post("/ask")
async def ask_tutor(
    body: AskRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    학생의 질문에 RAG 기반으로 루미 선생님이 답변합니다.

    [대화 기록 관리 방식 변경]
    기존: st.session_state['messages'] 에 서버 메모리로 저장
    변경: 클라이언트(HTML)가 chat_history 배열을 직접 관리하여 매 요청마다 전송
          → 서버는 Stateless 유지

    [기존 main.py 코드]
        response = ask_question_to_tutor(prompt, st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": response})

    [변경 후 HTML fetch 예시]
        // chatHistory 배열을 HTML JS에서 직접 관리
        chatHistory.push({ role: "user", content: userMessage });

        const res = await fetch("http://localhost:8000/api/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                question: userMessage,
                chat_history: chatHistory   // 누적된 대화 기록 전송
            })
        });
        const data = await res.json();
        chatHistory.push({ role: "assistant", content: data.answer });
        renderMessage(data.answer);
    """
    try:
        answer = await svc_ask_tutor(body.question, body.chat_history)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"질의응답 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑦ POST /api/evaluate  ─  학생 답변 채점
# ─────────────────────────────────────────────────────────
@router.post("/evaluate")
async def evaluate_student_answer(
    body: EvaluateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    학생의 답변을 채점하고 정답/오답 여부와 피드백을 반환합니다.

    [기존 main.py 코드]
        result = evaluate_answer(prob, ans)
        st.session_state['is_correct'] = "[정답]" in result

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/evaluate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                problem: currentProblem,       // /api/problem 에서 받은 문제 dict
                student_answer: answerInput    // 학생이 입력한 답변
            })
        });
        const data = await res.json();
        // { "feedback": "아쉬워요, 힌트는...", "is_correct": false }

        if (data.is_correct) {
            showCelebration();
        } else {
            showHint(data.feedback);
        }
    """
    try:
        result = await svc_grade_answer(body.problem, body.student_answer)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채점 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑧ POST /api/history  ─  학습 결과 저장
# ─────────────────────────────────────────────────────────
@router.post("/history")
async def record_history(
    body: SaveHistoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    문제 풀이 결과를 DB에 저장합니다.
    username은 토큰에서 자동으로 추출하므로 요청 body에 포함하지 않습니다.

    [기존 main.py 코드]
        save_history(st.session_state.get('username', 'user'),
                     st.session_state['current_problem']['ID'],
                     st.session_state['selected_unit'], is_correct)

    [변경 후 HTML fetch 예시]
        await fetch("http://localhost:8000/api/history", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                problem_id: currentProblem.ID,
                unit: currentProblem["단원"],
                is_correct: isCorrect
            })
        });
    """
    try:
        save_history(
            username=current_user["username"],
            problem_id=body.problem_id,
            unit=body.unit,
            is_correct=body.is_correct
        )
        return {"message": "학습 기록이 저장되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학습 기록 저장 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑨ GET /api/history  ─  전체 학습 이력 조회 (리포트용)
# ─────────────────────────────────────────────────────────
@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    """
    현재 로그인 유저의 전체 학습 이력을 반환합니다.

    [기존 main.py 코드]
        history_df = get_user_history(st.session_state['username'])
        st.dataframe(history_df, use_container_width=True)
        correct_rate = history_df['is_correct'].mean() * 100

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/history", {
            headers: { "Authorization": "Bearer " + token }
        });
        const data = await res.json();
        // {
        //   "history": [{"unit":"분수","is_correct":1,"timestamp":"..."},...],
        //   "correct_rate": 75.0
        // }

        document.getElementById("correct-rate").innerText = data.correct_rate + "%";
    """
    try:
        df = get_user_history(current_user["username"])
        if df.empty:
            return {"history": [], "correct_rate": 0.0}

        correct_rate = round(df['is_correct'].mean() * 100, 1)
        return {
            "history": df.to_dict(orient="records"),
            "correct_rate": correct_rate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학습 이력 조회 실패: {str(e)}")


# ─────────────────────────────────────────────────────────
# ⑩ GET /api/history/incorrect  ─  오답 목록 조회
# ─────────────────────────────────────────────────────────
@router.get("/history/incorrect")
async def get_incorrect(current_user: dict = Depends(get_current_user)):
    """
    한 번도 맞히지 못한 문제 목록을 반환합니다. (오답 노트용)

    [기존 main.py 코드]
        wrong_problems = get_incorrect_problems(st.session_state['username'])
        for p in wrong_problems:
            with st.expander(f"{p['단원']} (ID: {p['ID']})"):
                st.markdown(p['문제'])

    [변경 후 HTML fetch 예시]
        const res = await fetch("http://localhost:8000/api/history/incorrect", {
            headers: { "Authorization": "Bearer " + token }
        });
        const data = await res.json();
        // { "incorrect_problems": [ {ID, 단원, 문제, 풀이및정답, ...}, ... ] }

        data.incorrect_problems.forEach(p => {
            const card = document.createElement("div");
            card.innerHTML = `<h4>${p["단원"]} (ID: ${p["ID"]})</h4>
                              <p>${p["문제"]}</p>`;
            document.getElementById("wrong-note").appendChild(card);
        });
    """
    try:
        problems = get_incorrect_problems(current_user["username"])
        return {"incorrect_problems": problems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"오답 조회 실패: {str(e)}")