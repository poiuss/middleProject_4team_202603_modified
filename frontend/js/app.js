const API = "http://localhost:8000";
let currentPage = null;

// ==========================================
// 인증 유틸리티
// ==========================================

function renderMath(targetId) {
  if (!window.MathJax) return;
  const el = document.getElementById(targetId);
  if (!el) return;
  MathJax.typesetPromise([el]).catch((err) =>
    console.error("MathJax 렌더링 오류:", err)
  );
}

/**
 * 화면 표시용 문자열 정리
 * - 이미 LaTeX($, \frac 등)가 있으면 그대로 둠
 * - 일반 문자열에 1/3 같은 분수가 있으면 MathJax용 분수로 바꿈
 */
function prepareMathDisplayText(text) {
  const raw = String(text || "");

  // 이미 LaTeX가 들어있는 문자열은 그대로 사용
  if (/[\\$]/.test(raw)) {
    return raw;
  }

  // 일반 텍스트 안의 분수만 예쁘게 보이도록 변환
  return raw.replace(/(\d+)\s*\/\s*(\d+)/g, "\\(\\frac{$1}{$2}\\)");
}

/**
 * 콘솔 표시용 문자열 정리
 * - 콘솔은 MathJax 렌더링이 안 되니까 읽기 쉽게만 변환
 */
function formatMathForConsole(text) {
  return String(text || "")
    .replace(/\\\(/g, "")
    .replace(/\\\)/g, "")
    .replace(/\$/g, "")
    .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, "$1/$2")
    .replace(/\\times/g, "×")
    .replace(/\\div/g, "÷")
    .replace(/\\cdot/g, "·")
    .replace(/\\left/g, "")
    .replace(/\\right/g, "")
    .replace(/\\mathrm\{([^}]+)\}/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * 화면 출력 공통 함수
 * - 오늘학습 안의 설명/문제/피드백을 같은 방식으로 처리
 */
function setMathText(targetId, text) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.innerText = prepareMathDisplayText(text);
  renderMath(targetId);
}

/**
 * 일반 텍스트 출력 함수
 * - MathJax 없이 그대로 보여줄 때 사용
 */
function setPlainText(targetId, text) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.innerText = String(text || "");
}

/**
 * 콘솔 출력 공통 함수
 * - 오늘학습 안의 콘솔 출력 형식을 통일
 */
function logMathText(label, text) {
  console.log(`${label}:`, formatMathForConsole(text));
}

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
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

// ==========================================
// 로그인
// ==========================================

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

    const title = document.getElementById("sidebar-title");
    if (title) {
      title.innerText = `🎓 ${user.username}의 교실`;
    }

    goPage("today");
  } catch {
    window.location.href = "login.html";
  }
}

// ==========================================
// 페이지 라우팅
// ==========================================

async function _baseGoPage(pageName, force = false) {
  if (!force && currentPage === pageName) return;

  currentPage = pageName;

  const res = await fetch(`pages/${pageName}.html`);
  const html = await res.text();
  document.getElementById("page-container").innerHTML = html;

  if (pageName === "today") {
    renderToday();
    await loadUnits();
  }
}

let goPage = _baseGoPage;

function goHome() {
  localStorage.setItem("step", "select_unit");
  goPage("today", true);
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
    "evaluation",
  ];

  steps.forEach((s) => {
    const el = document.getElementById(`step-${s}`);
    if (!el) return;
    el.style.display = s === step ? "block" : "none";
  });

  const bindOnce = (id, handler) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", handler);
  };

  // 피드백 복원
  const savedFeedback = localStorage.getItem("last_feedback");
  if (savedFeedback) {
    setMathText("ai-feedback", savedFeedback);
  }

  // STEP: select_unit → explain
  bindOnce("btn-start", async () => {
    const unit = document.getElementById("unit-select")?.value;
    if (!unit) return;

    localStorage.setItem("selected_unit", unit);

    const t1 = document.getElementById("unit-title-explain");
    const t2 = document.getElementById("unit-title-student");
    if (t1) t1.innerText = unit;
    if (t2) t2.innerText = unit;

    setMathText("explain-text", "루미 선생님이 설명을 준비 중이에요... 🐰");

    try {
      const res = await apiFetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unit_name: unit }),
      });

      const data = await res.json();
      const explanation = data.explanation || "설명이 없습니다.";

      setMathText("explain-text", explanation);
      localStorage.setItem("current_explanation", explanation);

      // 설명도 콘솔 형식 통일
      logMathText("설명", explanation);
    } catch {
      setMathText("explain-text", "설명을 불러오는 데 실패했어요.");
    }

    localStorage.setItem("step", "explain");
    renderToday();
  });

  // explain → student_explain
  bindOnce("btn-go-student", () => {
    localStorage.setItem("step", "student_explain");
    renderToday();
  });

  // student_explain → explain_feedback
  bindOnce("btn-student-done", async () => {
    const studentText = document.getElementById("student-text")?.value || "";
    const unit = localStorage.getItem("selected_unit");

    setMathText("concept-feedback", "평가 중이에요... 잠깐만요 🐰");

    localStorage.setItem("step", "explain_feedback");
    renderToday();

    try {
      const res = await apiFetch("/api/explain/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept: unit,
          student_explanation: studentText,
        }),
      });

      const data = await res.json();
      const feedback = data.feedback || "평가 결과가 없습니다.";

      setMathText("concept-feedback", feedback);
      logMathText("이해도 피드백", feedback);

      localStorage.setItem("is_passed", data.is_passed ? "1" : "0");

      const btnQuiz = document.getElementById("btn-go-quiz");
      const btnReexplain = document.getElementById("btn-go-reexplain");

      if (data.is_passed) {
        if (btnQuiz) btnQuiz.style.display = "inline-block";
        if (btnReexplain) btnReexplain.style.display = "none";
      } else {
        if (btnQuiz) btnQuiz.style.display = "none";
        if (btnReexplain) btnReexplain.style.display = "inline-block";
      }
    } catch {
      setMathText("concept-feedback", "평가를 불러오는 데 실패했어요.");
    }
  });

  // explain_feedback → ask_question
  bindOnce("btn-go-quiz", async () => {
    await loadProblem();
    localStorage.setItem("step", "ask_question");
    renderToday();
  });

  // explain_feedback → re_explain
  bindOnce("btn-go-reexplain", () => {
    const explanation =
      localStorage.getItem("current_explanation") ||
      "설명을 다시 불러올 수 없어요.";

    setMathText("reexplain-text", explanation);
    logMathText("보충 설명", explanation);

    localStorage.setItem("step", "re_explain");
    renderToday();
  });

  // re_explain → ask_question
  bindOnce("btn-reexplain-done", async () => {
    await loadProblem();
    localStorage.setItem("step", "ask_question");
    renderToday();
  });

  // ask_question → evaluation
  bindOnce("btn-submit", async () => {
    const studentAnswer = document.getElementById("answer-text")?.value || "";
    const problem = JSON.parse(localStorage.getItem("current_problem") || "{}");

    localStorage.setItem("step", "evaluation");
    renderToday();

    setMathText("ai-feedback", "채점 중이에요... 🐰");

    try {
      const res = await apiFetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ problem, student_answer: studentAnswer }),
      });

      const data = await res.json();
      const feedback = data.feedback || "피드백이 없습니다.";

      localStorage.setItem("last_feedback", feedback);
      setMathText("ai-feedback", feedback);
      logMathText("최종 피드백", feedback);

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
      setMathText("ai-feedback", "채점을 불러오는 데 실패했어요.");
    }
  });

  // evaluation → ask_question
  bindOnce("btn-next-problem", async () => {
    localStorage.removeItem("last_feedback");
    await loadProblem();
    localStorage.setItem("step", "ask_question");
    renderToday();
  });

  // evaluation → select_unit
  bindOnce("btn-next-unit", () => {
    localStorage.removeItem("last_feedback");
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
  const quizId = document.getElementById("quiz-id");

  try {
    const res = await apiFetch(`/api/problem?unit=${encodeURIComponent(unit)}`);
    const data = await res.json();
    const prob = data.problem;

    localStorage.setItem("current_problem", JSON.stringify(prob));

    // 콘솔 출력도 공통 형식으로 통일
    logMathText("문제", prob["문제"] || "");
    logMathText(
      "정답",
      prob.answer || prob["정답"] || prob["답"] || prob["풀이및정답"] || ""
    );

    if (quizId) quizId.innerText = prob.ID ?? "-";

    if (problemBox) {
      setMathText("quiz-problem", prob["문제"] ?? "문제를 불러올 수 없어요.");
    }

    if (data.image_b64 && problemBox) {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${data.image_b64}`;
      img.style.maxWidth = "100%";
      problemBox.appendChild(img);
    }
  } catch {
    if (problemBox) {
      setMathText("quiz-problem", "문제를 불러오는 데 실패했어요.");
    }
  }
}

// ==========================================
// 단원 목록 초기화
// ==========================================

async function loadUnits() {
  const select = document.getElementById("unit-select");
  if (!select) return;

  try {
    const res = await apiFetch("/api/units");
    const data = await res.json();

    select.innerHTML = `<option value="">단원 선택</option>`;
    (data.units || []).forEach((unit) => {
      const opt = document.createElement("option");
      opt.value = unit;
      opt.text = unit;
      select.add(opt);
    });
  } catch {
    console.error("단원 목록 로드 실패");
  }
}