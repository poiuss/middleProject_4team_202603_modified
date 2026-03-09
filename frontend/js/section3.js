document.addEventListener("DOMContentLoaded", () => {
  const examCard = document.querySelector("#page-exam .card");
  if (!examCard) return;

  examCard.innerHTML = `
    <h2>시험 단원 선택</h2>

    <div class="row">
      <select>
        <option>단원 선택</option>
        <option>공배수와 최소공배수</option>
        <option>약수와 배수</option>
        <option>분수의 덧셈과 뺄셈</option>
      </select>

      <button>시험지 만들기</button>
      <button>시험 시작</button>
    </div>

    <div class="box" style="margin-top:20px;">
      ⏰ 남은 시간 : 40:00
    </div>

    <div style="margin-top:20px;">
      <p><b>1번.</b> 3과 5의 최소공배수는 무엇인가요?</p>
      <input type="text" placeholder="답 입력">
    </div>

    <div style="margin-top:10px;">
      <p><b>2번.</b> 4와 6의 최소공배수를 구하세요.</p>
      <input type="text" placeholder="답 입력">
    </div>

    <div style="margin-top:10px;">
      <p><b>3번.</b> 8의 배수 3개를 쓰세요.</p>
      <input type="text" placeholder="답 입력">
    </div>

    <div style="margin-top:20px;">
      <button id="exam-submit-btn">시험 제출</button>
    </div>
  `;

  const submitBtn = document.getElementById("exam-submit-btn");
  if (!submitBtn) return;

  submitBtn.addEventListener("click", () => {
    const modal = document.getElementById("resultModal");
    const resultTitle = document.getElementById("resultTitle");
    const resultMessage = document.getElementById("resultMessage");
    const solutionText = document.getElementById("solutionText");
    const resultActionBtn = document.getElementById("resultActionBtn");
    const ttsBtn = document.getElementById("ttsBtn");

    if (!modal || !resultTitle || !resultMessage || !solutionText || !resultActionBtn || !ttsBtn) return;

    resultTitle.textContent = "시험 결과";
    resultMessage.innerHTML = `
      <p><strong>점수:</strong> 85점</p>
      <p><strong>틀린 문제:</strong> 2번</p>
      <p><strong>오답 안내:</strong> 최소공배수를 구할 때 공통으로 나오는 가장 작은 배수를 찾아야 해.</p>
    `;
    solutionText.textContent =
      "4와 6의 배수를 각각 써보면 4의 배수는 4, 8, 12, 16... 이고 6의 배수는 6, 12, 18... 이야. 처음으로 공통으로 나오는 수는 12이므로 최소공배수는 12야.";
    resultActionBtn.textContent = "확인";
    ttsBtn.textContent = "음성 듣기";

    modal.classList.remove("hidden");
    modal.style.display = "flex";
  });
});