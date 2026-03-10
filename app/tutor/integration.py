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

DATA_PATH = 'data/processed/math_tutor_dataset.csv'

load_dotenv()
client = OpenAI()
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)


# ==========================================
# 1. 일반 함수 및 Tools
# ==========================================

def generate_speech_with_cache(text: str) -> bytes:
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
    """수학 튜터 데이터셋에 있는 전체 단원 목록을 반환합니다."""
    df = pd.read_csv(DATA_PATH)
    return sorted(df['단원'].unique().tolist())


@tool
def get_problem_by_unit(unit_name: str) -> dict:
    """선택한 단원에서 문제 하나를 무작위로 반환합니다."""
    df = pd.read_csv(DATA_PATH)
    unit_df = df[df['단원'] == unit_name]

    if not unit_df.empty:
        return unit_df.sample(n=1).iloc[0].to_dict()

    return None


# ⭐ 시험용 문제 추출 (주석님 기능 추가)

def get_exam_problems(unit_name: str, n: int =3) -> list:

    df = pd.read_csv(DATA_PATH)
    unit_df = df[df['단원'] == unit_name]

    if unit_df.empty:
        return []

    k = min(n, len(unit_df))

    problems = unit_df.sample(n=k).to_dict("records")

    return [
        {key: (None if str(val) == "nan" else val) for key, val in p.items()}
        for p in problems
    ]


# ==========================================
# 2. LangChain 체인
# ==========================================

explain_prompt = ChatPromptTemplate.from_messages([
    ("system", """너는 수학 선생님인 토끼 캐릭터 '루미'야.
초등학교 5학년 학생들에게 아주 친절하고 쉽게 설명해줘.
'{unit_name}' 단원을 재미있는 예시로 설명해줘.""")
])

explain_chain = explain_prompt | llm | StrOutputParser()


def explain_concept(unit_name: str) -> str:
    return explain_chain.invoke({"unit_name": unit_name})


concept_eval_prompt = ChatPromptTemplate.from_messages([
    ("system", """초등학교 5학년 수학 선생님입니다.
학생이 '{concept}'을 설명했습니다.

이해가 충분하면 마지막에 [PASS]
부족하면 [FAIL]을 적어주세요."""),
    ("user", "{student_explanation}")
])

concept_chain = concept_eval_prompt | llm | StrOutputParser()


answer_eval_prompt = ChatPromptTemplate.from_messages([
    ("system", """초등학교 5학년 수학 선생님입니다.

숫자와 수식은 LaTeX $...$ 형식으로 표현하세요.

문제: {problem_question}
정답 및 풀이: {problem_solution}

마지막 줄에 반드시 [정답] 또는 [오답]을 적으세요."""),
    ("user", "{student_answer}")
])

answer_chain = answer_eval_prompt | llm | StrOutputParser()


# ==========================================
# 3. Q&A 챗봇
# ==========================================

_QA_SYSTEM_PROMPT = """너는 수학 선생님 '루미'야.
초등학생 질문에 친절하게 답해줘.
수식은 $...$ 형식으로 표현해."""


def ask_question_to_tutor(question: str, chat_history: list) -> str:

    messages = [SystemMessage(content=_QA_SYSTEM_PROMPT)]

    for turn in chat_history:
        role = turn.get("role", "")
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
        return f"오류 발생: {e}"


# ==========================================
# 4. LangGraph 상태
# ==========================================

class TutorState(TypedDict):

    units: Optional[list]
    selected_unit: Optional[str]
    problem: Optional[Dict]

    task_type: Optional[str]
    student_explanation: Optional[str]
    student_answer: Optional[str]
    feedback: Optional[str]

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

    feedback = concept_chain.invoke({
        "concept": state["selected_unit"],
        "student_explanation": state["student_explanation"]
    })

    return {"feedback": feedback}


def evaluate_answer_node(state: TutorState) -> Dict[str, Any]:

    problem = state["problem"]

    feedback = answer_chain.invoke({
        "problem_question": problem["문제"],
        "problem_solution": problem["풀이"],
        "correct_answer": problem["정답"],
        "student_answer": state["student_answer"]
    })

    return {"feedback": feedback}


def entry_router(state: TutorState) -> str:

    task = state.get("task_type")

    if task == "concept":
        return "eval_concept"

    elif task == "answer":
        return "eval_answer"

    return "get_units"


# ==========================================
# 5. Graph 구성
# ==========================================

workflow = StateGraph(TutorState)

workflow.add_node("get_units", fetch_units_node)
workflow.add_node("get_problem", fetch_problem_node)
workflow.add_node("eval_concept", evaluate_concept_node)
workflow.add_node("eval_answer", evaluate_answer_node)

workflow.set_conditional_entry_point(
    entry_router,
    {
        "get_units": "get_units",
        "eval_concept": "eval_concept",
        "eval_answer": "eval_answer"
    }
)

workflow.add_edge("get_units", "get_problem")
workflow.add_edge("get_problem", END)
workflow.add_edge("eval_concept", END)
workflow.add_edge("eval_answer", END)

tutor_app = workflow.compile()


# ==========================================
# 6. Wrapper
# ==========================================

def get_problem_workflow(unit_name: str):
    return tutor_app.invoke({"selected_unit": unit_name, "messages": []})


def evaluate_concept_understanding(concept: str, student_explanation: str):

    result = tutor_app.invoke({
        "task_type": "concept",
        "selected_unit": concept,
        "student_explanation": student_explanation,
        "messages": []
    })

    return result.get("feedback")


def evaluate_answer(problem: dict, student_answer: str):

    result = tutor_app.invoke({
        "task_type": "answer",
        "problem": problem,
        "student_answer": student_answer,
        "messages": []
    })

    return result.get("feedback")