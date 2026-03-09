document.addEventListener("DOMContentLoaded", () => {
  const scoreCard = document.querySelector("#page-score .card");
  if (!scoreCard) return;

  scoreCard.innerHTML = `
    <div class="score-dashboard">

      <h2>시험 기록 요약</h2>
      <div class="score-summary">
        <div class="summary-card">
          <div class="summary-label">최근 시험 단원</div>
          <div class="summary-value">공배수와 최소공배수</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">최근 점수</div>
          <div class="summary-value">85점</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">평균 점수</div>
          <div class="summary-value">78점</div>
        </div>
      </div>

      <h2>점수 변화 그래프</h2>
      <div class="graph-card">
        <svg width="100%" height="260" viewBox="0 0 800 260">
          <line x1="60" y1="20" x2="60" y2="210" stroke="#999" stroke-width="2"/>
          <line x1="60" y1="210" x2="740" y2="210" stroke="#999" stroke-width="2"/>

          <text x="20" y="30" font-size="14">100</text>
          <text x="28" y="75" font-size="14">80</text>
          <text x="28" y="120" font-size="14">60</text>
          <text x="28" y="165" font-size="14">40</text>
          <text x="28" y="210" font-size="14">20</text>

          <polyline
            fill="none"
            stroke="#222"
            stroke-width="4"
            points="100,170 200,145 300,120 400,135 500,95 600,80 700,60" />

          <circle cx="100" cy="170" r="6" fill="#222"/>
          <circle cx="200" cy="145" r="6" fill="#222"/>
          <circle cx="300" cy="120" r="6" fill="#222"/>
          <circle cx="400" cy="135" r="6" fill="#222"/>
          <circle cx="500" cy="95" r="6" fill="#222"/>
          <circle cx="600" cy="80" r="6" fill="#222"/>
          <circle cx="700" cy="60" r="6" fill="#222"/>

          <text x="85" y="235" font-size="13">1회</text>
          <text x="185" y="235" font-size="13">2회</text>
          <text x="285" y="235" font-size="13">3회</text>
          <text x="385" y="235" font-size="13">4회</text>
          <text x="485" y="235" font-size="13">5회</text>
          <text x="585" y="235" font-size="13">6회</text>
          <text x="685" y="235" font-size="13">7회</text>
        </svg>
      </div>

      <h2>시험 기록 목록</h2>
      <div class="log-card">
        <table class="score-table">
          <thead>
            <tr>
              <th>날짜</th>
              <th>단원</th>
              <th>점수</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>2026-03-01</td>
              <td>약수와 배수</td>
              <td>55점</td>
              <td><span class="status-badge danger">복습 필요</span></td>
            </tr>
            <tr>
              <td>2026-03-03</td>
              <td>공배수와 최소공배수</td>
              <td>68점</td>
              <td><span class="status-badge up">상승 중</span></td>
            </tr>
            <tr>
              <td>2026-03-05</td>
              <td>분수의 덧셈과 뺄셈</td>
              <td>82점</td>
              <td><span class="status-badge good">좋아요</span></td>
            </tr>
            <tr>
              <td>2026-03-07</td>
              <td>소수의 덧셈과 뺄셈</td>
              <td>85점</td>
              <td><span class="status-badge stable">안정적</span></td>
            </tr>
          </tbody>
        </table>
      </div>

    </div>
  `;
});