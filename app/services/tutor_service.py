"""
services/tutor_service.py  ─  튜터 로직 서비스 계층
"""

import os
import base64
import zipfile
import asyncio

from app.tutor.integration import (
    explain_concept,
    ask_question_to_tutor,
    evaluate_answer,
    evaluate_concept_understanding,
    get_units,
    get_problem_by_unit,
    get_exam_problems,
)


async def fetch_units() -> list[str]:
    return get_units.invoke({})


async def fetch_problem(unit_name: str) -> dict | None:
    return get_problem_by_unit.invoke({"unit_name": unit_name})


def get_problem_image_b64(problem_id: str) -> str | None:
    """문제 ID에 해당하는 이미지를 base64로 반환. 없으면 None."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_path = os.path.join(base_dir, "data", "raw")
    target_id = str(problem_id).strip()
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
            if file.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(os.path.join(root, file), "r") as z:
                        for name in z.namelist():
                            bn = os.path.basename(name).lower()
                            if target_id in bn and any(bn.endswith(e.lower()) for e in valid_exts):
                                return base64.b64encode(z.read(name)).decode("utf-8")
                except Exception:
                    continue
    return None


async def get_explanation(unit_name: str) -> str:
    return explain_concept(unit_name)


async def evaluate_explanation(concept: str, student_explanation: str) -> dict:
    feedback = evaluate_concept_understanding(concept, student_explanation)
    is_passed = "[PASS]" in feedback.upper()
    return {"feedback": feedback, "is_passed": is_passed}


async def ask_tutor(question: str, chat_history: list) -> str:
    return ask_question_to_tutor(question, chat_history)


async def grade_answer(problem: dict, student_answer: str) -> dict:
    feedback = evaluate_answer(problem, student_answer)
    is_correct = "[정답]" in feedback
    return {"feedback": feedback, "is_correct": is_correct}


# ─────────────────────────────────────────────────────────
# 시험 관련 서비스 함수
# ─────────────────────────────────────────────────────────

async def generate_exam_questions(unit_name: str) -> list:
    return get_exam_problems(unit_name, n=10)


async def grade_exam_answers(problems: list, answers: list) -> dict:

    def grade_one_sync(problem, answer):
        if not answer or not str(answer).strip():
            return {"feedback": "답을 입력하지 않았습니다.\n\n[오답]", "is_correct": False}
        try:
            feedback = evaluate_answer(problem, answer)
            return {"feedback": feedback, "is_correct": "[정답]" in feedback}
        except Exception as e:
            return {"feedback": f"채점 중 오류가 발생했습니다. [오답] ({e})", "is_correct": False}

    results = await asyncio.gather(*[
        asyncio.to_thread(
            grade_one_sync,
            problems[i],
            answers[i] if i < len(answers) else ""
        )
        for i in range(len(problems))
    ])

    correct_count = sum(1 for r in results if r["is_correct"])
    total = len(problems)
    score = round(correct_count / total * 100) if total > 0 else 0

    wrong_numbers = [i + 1 for i, r in enumerate(results) if not r["is_correct"]]
    feedbacks = {
        str(i + 1): results[i]["feedback"]
        for i in range(len(results))
        if not results[i]["is_correct"]
    }

    return {
        "score": score,
        "total": total,
        "correct": correct_count,
        "wrong_numbers": wrong_numbers,
        "feedbacks": feedbacks,
    }