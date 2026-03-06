import os
import hashlib
import pandas as pd
from typing import TypedDict, Optional, Dict, Any, Annotated
from dotenv import load_dotenv

from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# 기존 변수 유지
DATA_PATH = 'data/processed/math_tutor_dataset.csv'

load_dotenv()
client = OpenAI()
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)

# ==========================================
# 1. 일반 함수 및 LangChain Tools 정의
# ==========================================

def generate_speech_with_cache(text: str) -> bytes:
    """설명 텍스트를 음성으로 변환 (캐싱 적용)"""
    text_hash = hashlib.md5(text.encode()).hexdigest()
    audio_dir = "assets/audio"
    
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)
        
    file_path = os.path.join(audio_dir, f"{text_hash}.mp3")

    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return f.read()

    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova", 
            input=text
        )
        response.write_to_file(file_path)
        with open(file_path, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"❌ 음성 생성 오류: {e}")
        return None

@tool
def get_units() -> list:
    """수학 튜터 데이터셋(DB)에 있는 모든 단원 목록을 정렬하여 반환합니다."""
    df = pd.read_csv(DATA_PATH)
    return sorted(df['단원'].unique().tolist())

@tool
def get_problem_by_unit(unit_name: str) -> dict:
    """선택한 단원에서 문제 하나를 무작위로 가져옵니다."""
    df = pd.read_csv(DATA_PATH)
    unit_df = df[df['단원'] == unit_name]
    if not unit_df.empty:
        return unit_df.sample(n=1).iloc[0].to_dict()
    return None

# ==========================================
# 2. LangChain 체인 (개념 설명 & 평가)
# ==========================================

# 개념 설명 체인
explain_prompt = ChatPromptTemplate.from_messages([
    ("system", """너는 수학 선생님인 토끼 캐릭터 '루미'야. 초등학교 5학년 학생들에게 아주 친절하고 상냥하게 말해줘.
    학생이 선택한 '{unit_name}' 단원에 대해 아주 쉽고 재미있는 비유를 들어서 설명해줘.""")
])
explain_chain = explain_prompt | llm | StrOutputParser()

def explain_concept(unit_name: str) -> str:
    return explain_chain.invoke({"unit_name": unit_name})

# 개념 평가 체인
concept_eval_prompt = ChatPromptTemplate.from_messages([
    ("system", """당신은 초등학교 5학년 수학 선생님입니다. 학생이 '{concept}'에 대해 설명한 내용을 듣고 평가해주세요.
    이해도가 충분하면 마지막에 [PASS], 부족하면 [FAIL]이라고 적어주세요."""),
    ("user", "{student_explanation}")
])
concept_chain = concept_eval_prompt | llm | StrOutputParser()

# 답변 평가 체인
answer_eval_prompt = ChatPromptTemplate.from_messages([
    ("system", """너는 초등학교 5학년 수학 선생님이야. 
    모든 숫자와 연산 기호는 LaTeX 형식인 $ 기호로 감싸서 표현해. (예: $5000 + 3000$)
    분수는 \\frac{{분자}}{{분모}} 형식을 사용해. (예: $\\frac{{1}}{{2}}$)
    
    [문제 정보]
    문제: {problem_question}
    정답 및 풀이: {problem_solution}

    마지막 줄에 반드시 [정답] 또는 [오답]이라고 명확하게 적어줘."""),
    ("user", "{student_answer}")
])
answer_chain = answer_eval_prompt | llm | StrOutputParser()

# ──────────────────────────────────────────────────────────────
# [추가] Q&A 챗봇 체인
#
# [추가 이유]
# tutor_service.py의 ask_tutor()가 아래 함수를 명시적으로 import합니다:
#   from app.tutor.integration import ask_question_to_tutor
# Integration.py 원본에 이 함수가 없어 서버 기동 시 ImportError가 발생합니다.
#
# [설계 원칙]
# - 기존 LangChain 체인 스타일(prompt | llm | parser)을 그대로 따릅니다.
# - 대화 기록(chat_history)은 클라이언트가 매 요청마다 전달 → 서버 Stateless 유지
# - TutorState의 messages 필드와 연동 가능하도록 HumanMessage/AIMessage 형식 사용
# ──────────────────────────────────────────────────────────────

_QA_SYSTEM_PROMPT = """너는 수학 선생님인 토끼 캐릭터 '루미'야.
초등학교 5학년 학생들의 수학 질문에 친절하고 쉽게 답해줘.
- 모든 숫자와 수식은 LaTeX($...$) 형식으로 표현해.
- 비유와 예시를 적극 활용해.
- 정답을 바로 알려주기보다 힌트를 먼저 줘서 스스로 생각하게 해줘."""

def ask_question_to_tutor(question: str, chat_history: list) -> str:
    """
    학생의 질문에 루미 선생님이 대화 맥락을 유지하며 답변합니다.

    Args:
        question     : 학생의 현재 질문 문자열
        chat_history : [{"role": "user"|"assistant", "content": "..."}, ...] 형식의 이전 대화

    반환 예시:
        "좋은 질문이야! 분모가 다를 때는 먼저 통분을 해야 해 🐰 ..."
    """
    messages = [SystemMessage(content=_QA_SYSTEM_PROMPT)]

    for turn in chat_history:
        role    = turn.get("role", "")
        content = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=question))

    try:
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        return f"죄송해, 지금 잠깐 문제가 생겼어. 다시 질문해줄래? 🐰 (오류: {e})"

# ==========================================
# 3. 통합 LangGraph 상태(State) 및 노드(Node) 정의
# ==========================================

class TutorState(TypedDict):
    # 단위 및 문제 추출용
    units: Optional[list]
    selected_unit: Optional[str]
    problem: Optional[Dict]
    
    # 평가 및 피드백용
    task_type: Optional[str] # 'concept' 또는 'answer'
    student_explanation: Optional[str]
    student_answer: Optional[str]
    feedback: Optional[str]
    
    # Q&A 챗봇용
    messages: Annotated[list, add_messages]
    context: Optional[str]

def fetch_units_node(state: TutorState) -> Dict[str, Any]:
    return {"units": get_units.invoke({})}

def fetch_problem_node(state: TutorState) -> Dict[str, Any]:
    unit_name = state.get("selected_unit")
    if unit_name:
        return {"problem": get_problem_by_unit.invoke({"unit_name": unit_name})}
    return {"problem": None}

def evaluate_concept_node(state: TutorState) -> Dict[str, Any]:
    try:
        feedback = concept_chain.invoke({
            "concept": state["selected_unit"],
            "student_explanation": state["student_explanation"]
        })
        return {"feedback": feedback}
    except Exception:
        return {"feedback": "이해도를 확인하는 중 오류가 발생했습니다. \n\n[FAIL]"}

def evaluate_answer_node(state: TutorState) -> Dict[str, Any]:
    try:
        problem = state["problem"]
        feedback = answer_chain.invoke({
            "problem_question": problem['문제'],
            "problem_solution": problem['풀이및정답'],
            "student_answer": state["student_answer"]
        })
        return {"feedback": feedback}
    except Exception:
        return {"feedback": "채점 시스템에 잠시 문제가 생겼어요. \n\n[오답]"}

def entry_router(state: TutorState) -> str:
    """
    시작 노드에서 task_type에 따라 목적지 노드를 직접 반환합니다.

    [수정 이유]
    기존 set_conditional_entry_point의 두 번째 인자에
    { "route": route_evaluation 함수 } 처럼 함수 객체를 값으로 넘기는
    2단계 라우팅 구조는 최신 LangGraph에서 지원되지 않습니다.
    (ValueError: unknown target '<function route_evaluation ...>')

    수정: 조건 함수 하나가 최종 노드 이름 문자열을 직접 반환하도록 통합합니다.
    """
    task = state.get("task_type")
    if task == "concept":
        return "eval_concept"
    elif task == "answer":
        return "eval_answer"
    return "get_units"

# ==========================================
# 4. LangGraph 그래프 생성 및 컴파일
# ==========================================

workflow = StateGraph(TutorState)

# 노드 등록
workflow.add_node("get_units", fetch_units_node)
workflow.add_node("get_problem", fetch_problem_node)
workflow.add_node("eval_concept", evaluate_concept_node)
workflow.add_node("eval_answer", evaluate_answer_node)

# 워크플로우 엣지 설정
# 조건 함수가 반환하는 문자열 → 노드 이름 매핑을 명시적으로 선언
workflow.set_conditional_entry_point(
    entry_router,
    {
        "get_units":    "get_units",
        "eval_concept": "eval_concept",
        "eval_answer":  "eval_answer",
    }
)

workflow.add_edge("get_units", "get_problem")
workflow.add_edge("get_problem", END)
workflow.add_edge("eval_concept", END)
workflow.add_edge("eval_answer", END)

tutor_app = workflow.compile()

# ==========================================
# 5. 실행을 위한 래퍼(Wrapper) 함수
# ==========================================

def get_problem_workflow(unit_name: str):
    """단원명으로 문제를 가져오는 워크플로우"""
    result = tutor_app.invoke({"selected_unit": unit_name, "messages": []})
    return result

def evaluate_concept_understanding(concept: str, student_explanation: str):
    """개념 이해도 평가 래퍼"""
    result = tutor_app.invoke({
        "task_type": "concept",
        "selected_unit": concept,
        "student_explanation": student_explanation,
        "messages": []
    })
    return result.get("feedback")

def evaluate_answer(problem: dict, student_answer: str):
    """문제 답변 평가 래퍼"""
    result = tutor_app.invoke({
        "task_type": "answer",
        "problem": problem,
        "student_answer": student_answer,
        "messages": []
    })
    return result.get("feedback")