const API = "http://localhost:8000";

// ==========================================
// 인증 유틸리티
// ==========================================

function getToken() {
  return sessionStorage.getItem("token");
}

/**
 * JWT 토큰을 Authorization 헤더에 포함한 fetch 래퍼.
 * 모든 API 호출은 이 함수를 통해 보냅니다.
 */
async function apiFetch(path, options = {}) {
  const token = getToken();
  return fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    },
  });
}

// ==========================================
// 로그인
// ==========================================

/**
 * [수정 사항 4가지]
 * 1. 엔드포인트: "/login" → "http://localhost:8000/auth/login"
 * 2. Content-Type: "application/json" → "application/x-www-form-urlencoded"
 *    (OAuth2PasswordRequestForm은 form 형식만 허용)
 * 3. 응답 판별: data.success → data.access_token
 * 4. 저장: localStorage("username") → sessionStorage("token") + ("username")
 */
async function login() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });

    const data = await response.json();

    if (data.access_token) {
      sessionStorage.setItem("token", data.access_token);
      sessionStorage.setItem("username", data.username);
      window.location.href = "app.html";
      return;
    }

    document.getElementById("error-msg").innerText =
      data.detail || "아이디 또는 비밀번호가 일치하지 않습니다.";
  } catch (error) {
    document.getElementById("error-msg").innerText = "서버 연결 오류";
  }
}

// ==========================================
// 앱 초기화 (app.html 진입점)
// ==========================================

/**
 * [수정 사항]
 * 기존: localStorage.getItem("username") 존재 여부만 확인
 * 변경: sessionStorage의 토큰으로 /auth/me 호출 → 실제 서버 검증
 */
async function initApp() {
  const token = getToken();

  if (!token) {
    window.location.href = "login.html";
    return;
  }

  try {
    const res = await apiFetch("/auth/me");
    if (!res.ok) {
      sessionStorage.clear();
      window.location.href = "login.html";
      return;
    }
    const user = await res.json();
    sessionStorage.setItem("username", user.username);
    document.getElementById("sidebar-title").innerText = `🎓 ${user.username}의 교실`;
    goPage("today");
  } catch {
    window.location.href = "login.html";
  }
}

// ==========================================
// 페이지 라우팅
// ==========================================

async function goPage(pageName) {
  const res = await fetch(`pages/${pageName}.html`);
  const html = await res.text();
  document.getElementById("page-container").innerHTML = html;

  if (pageName === "today") {
    renderToday();
  }
}

function goHome() {
  localStorage.setItem("step", "select_unit");
  goPage("today");
}

// ==========================================
// 오늘 학습 렌더링 (step 기반 SPA)
// ==========================================

function renderToday() {
    const step = localStorage.getItem("step") || "select_unit";

    const steps = [
        "select_unit",
        "explain",
        "student_explain",
        "explain_feedback",
        "re_explain",
        "ask_question",
        "evaluation"
    ];

    steps.forEach((s) => {
        const el = document.getElementById(`step-${s}`);
        if (!el) return;
        el.style.display = (s === step) ? "block" : "none";
    });

    const bindOnce = (id, handler) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", handler);
    };

    // STEP: select_unit → explain (단원 선택 후 API로 단원 목록 로드)
    bindOnce("btn-start", async () => {
        const unit = document.getElementById("unit-select").value;
        if (!unit) return;

        localStorage.setItem("selected_unit", unit);

        const t1 = document.getElementById("unit-title-explain");
        const t2 = document.getElementById("unit-title-student");
        if (t1) t1.innerText = unit;
        if (t2) t2.innerText = unit;

        // 개념 설명 API 호출
        const explainBox = document.getElementById("explain-text");
        if (explainBox) explainBox.innerText = "루미 선생님이 설명을 준비 중이에요... 🐰";
        try {
            const res = await apiFetch("/api/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ unit_name: unit }),
            });
            const data = await res.json();
            if (explainBox) explainBox.innerText = data.explanation;
            localStorage.setItem("current_explanation", data.explanation);
        } catch {
            if (explainBox) explainBox.innerText = "설명을 불러오는 데 실패했어요.";
        }

        localStorage.setItem("step", "explain");
        renderToday();
    });

    // explain → student_explain
    bindOnce("btn-go-student", () => {
        localStorage.setItem("step", "student_explain");
        renderToday();
    });

    // student_explain → explain_feedback (이해도 평가 API 호출)
    bindOnce("btn-student-done", async () => {
        const studentText = document.getElementById("student-text")?.value || "";
        const unit = localStorage.getItem("selected_unit");
        const feedbackBox = document.getElementById("concept-feedback");

        if (feedbackBox) feedbackBox.innerText = "평가 중이에요... 잠깐만요 🐰";
        localStorage.setItem("step", "explain_feedback");
        renderToday();

        try {
            const res = await apiFetch("/api/explain/evaluate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ concept: unit, student_explanation: studentText }),
            });
            const data = await res.json();
            const fb = document.getElementById("concept-feedback");
            if (fb) fb.innerText = data.feedback;
            localStorage.setItem("is_passed", data.is_passed ? "1" : "0");

            // PASS/FAIL에 따라 버튼 표시 조정
            const btnQuiz     = document.getElementById("btn-go-quiz");
            const btnReexplain = document.getElementById("btn-go-reexplain");
            if (data.is_passed) {
                if (btnQuiz)      btnQuiz.style.display      = "inline-block";
                if (btnReexplain) btnReexplain.style.display = "none";
            } else {
                if (btnQuiz)      btnQuiz.style.display      = "none";
                if (btnReexplain) btnReexplain.style.display = "inline-block";
            }
        } catch {
            const fb = document.getElementById("concept-feedback");
            if (fb) fb.innerText = "평가를 불러오는 데 실패했어요.";
        }
    });

    // explain_feedback → ask_question (문제 로드)
    bindOnce("btn-go-quiz", async () => {
        await loadProblem();
        localStorage.setItem("step", "ask_question");
        renderToday();
    });

    // explain_feedback → re_explain (보충 설명 재노출)
    bindOnce("btn-go-reexplain", () => {
        const reBox = document.getElementById("reexplain-text");
        if (reBox) reBox.innerText = localStorage.getItem("current_explanation") || "설명을 다시 불러올 수 없어요.";
        localStorage.setItem("step", "re_explain");
        renderToday();
    });

    // re_explain → ask_question
    bindOnce("btn-reexplain-done", async () => {
        await loadProblem();
        localStorage.setItem("step", "ask_question");
        renderToday();
    });

    // ask_question → evaluation (채점 API 호출)
    bindOnce("btn-submit", async () => {
        const studentAnswer = document.getElementById("answer-text")?.value || "";
        const problem = JSON.parse(localStorage.getItem("current_problem") || "{}");

        localStorage.setItem("step", "evaluation");
        renderToday();

        const feedbackBox = document.getElementById("ai-feedback");
        if (feedbackBox) feedbackBox.innerText = "채점 중이에요... 🐰";

        try {
            const res = await apiFetch("/api/evaluate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ problem, student_answer: studentAnswer }),
            });
            const data = await res.json();
            if (feedbackBox) feedbackBox.innerText = data.feedback;

            // 학습 이력 저장
            await apiFetch("/api/history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    problem_id: String(problem.ID || ""),
                    unit: problem["단원"] || "",
                    is_correct: data.is_correct,
                }),
            });
        } catch {
            if (feedbackBox) feedbackBox.innerText = "채점을 불러오는 데 실패했어요.";
        }
    });

    // evaluation → ask_question (다른 문제)
    bindOnce("btn-next-problem", async () => {
        await loadProblem();
        localStorage.setItem("step", "ask_question");
        renderToday();
    });

    // evaluation → select_unit (다음 단원)
    bindOnce("btn-next-unit", () => {
        localStorage.setItem("step", "select_unit");
        renderToday();
    });
}

// ==========================================
// 문제 로드 헬퍼
// ==========================================

async function loadProblem() {
    const unit = localStorage.getItem("selected_unit");
    const problemBox = document.getElementById("quiz-problem");
    const quizId     = document.getElementById("quiz-id");

    try {
        const res  = await apiFetch(`/api/problem?unit=${encodeURIComponent(unit)}`);
        const data = await res.json();
        const prob = data.problem;

        localStorage.setItem("current_problem", JSON.stringify(prob));
        if (quizId)     quizId.innerText     = prob.ID ?? "-";
        if (problemBox) problemBox.innerText = prob["문제"] ?? "문제를 불러올 수 없어요.";

        // 이미지가 있으면 표시
        if (data.image_b64 && problemBox) {
            const img = document.createElement("img");
            img.src   = `data:image/png;base64,${data.image_b64}`;
            img.style.maxWidth = "100%";
            problemBox.appendChild(img);
        }
    } catch {
        if (problemBox) problemBox.innerText = "문제를 불러오는 데 실패했어요.";
    }
}

// ==========================================
// 단원 목록 초기화 (today.html 로드 후 호출)
// ==========================================

async function loadUnits() {
    const select = document.getElementById("unit-select");
    if (!select) return;

    try {
        const res  = await apiFetch("/api/units");
        const data = await res.json();

        // 기존 샘플 옵션 제거 후 API 결과로 교체
        select.innerHTML = `<option value="">단원 선택</option>`;
        (data.units || []).forEach(unit => {
            const opt = document.createElement("option");
            opt.value = unit;
            opt.text  = unit;
            select.add(opt);
        });
    } catch {
        console.error("단원 목록 로드 실패");
    }
}

// today.html이 page-container에 삽입된 후 단원 목록을 채웁니다.
const _origGoPage = typeof goPage !== "undefined" ? goPage : null;
