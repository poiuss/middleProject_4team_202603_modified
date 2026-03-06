"""
services/tutor_service.py  ─  튜터 로직 서비스 계층
"""

# ─── imports (파일 최상단) ───────────────────────────────
import os
import base64
import zipfile

# ✅ engine / evaluator / curator 모듈 대신
#     integration.py에서 직접 import
from app.tutor.integration import (
    explain_concept,
    ask_question_to_tutor,
    evaluate_answer,
    evaluate_concept_understanding,
    get_units,
    get_problem_by_unit,
)


async def fetch_units() -> list[str]:
    # @tool 데코레이터가 붙은 함수는 .invoke({}) 로 호출
    return get_units.invoke({})


async def fetch_problem(unit_name: str) -> dict | None:
    return get_problem_by_unit.invoke({"unit_name": unit_name})


def get_problem_image_b64(problem_id: str) -> str | None:
    """문제 ID에 해당하는 이미지를 base64로 반환. 없으면 None."""
    # app/services/tutor_service.py → ../../ 가 프로젝트 루트
    base_dir   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_path   = os.path.join(base_dir, "data", "raw")
    target_id  = str(problem_id).strip()
    valid_exts = ('.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG')

    if os.path.exists(raw_path):
        for root, dirs, files in os.walk(raw_path):
            for file in files:
                if target_id in file and file.endswith(valid_exts):
                    with open(os.path.join(root, file), "rb") as f:
                        return base64.b64encode(f.read()).decode("utf-8")

    data_path = os.path.join(base_dir, "data")
    for root, dirs, files in os.walk(data_path):
        for file in files:
            if file.lower().endswith('.zip'):
                try:
                    with zipfile.ZipFile(os.path.join(root, file), 'r') as z:
                        for name in z.namelist():
                            bn = os.path.basename(name).lower()
                            if target_id in bn and any(bn.endswith(e.lower()) for e in valid_exts):
                                return base64.b64encode(z.read(name)).decode("utf-8")
                except Exception:
                    continue
    return None


async def get_explanation(unit_name: str) -> str:
    """[랭그래프 교체 포인트] explain_concept → langgraph_agent.run"""
    return explain_concept(unit_name)


async def evaluate_explanation(concept: str, student_explanation: str) -> dict:
    """[랭그래프 교체 포인트] evaluate_concept_understanding → langgraph_agent.run"""
    feedback  = evaluate_concept_understanding(concept, student_explanation)
    is_passed = "[PASS]" in feedback.upper()
    return {"feedback": feedback, "is_passed": is_passed}


async def ask_tutor(question: str, chat_history: list) -> str:
    """[랭그래프 교체 포인트 - 핵심] ask_question_to_tutor → langgraph_agent.run"""
    return ask_question_to_tutor(question, chat_history)


async def grade_answer(problem: dict, student_answer: str) -> dict:
    """[랭그래프 교체 포인트] evaluate_answer → langgraph_agent.run"""
    feedback   = evaluate_answer(problem, student_answer)
    is_correct = "[정답]" in feedback
    return {"feedback": feedback, "is_correct": is_correct}