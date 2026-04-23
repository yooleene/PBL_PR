// 네이버 기자 분석기 - Main JS
// (Progress 폴링은 progress.html의 인라인 스크립트에서 처리)

document.addEventListener('DOMContentLoaded', function () {

  // ---- 검색 폼 입력 개선 ----
  const mediaInput = document.getElementById('media_name');
  const journalistInput = document.getElementById('journalist_name');

  // 엔터키로 다음 필드 이동
  if (mediaInput) {
    mediaInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (journalistInput) journalistInput.focus();
      }
    });
  }

  // ---- 결과 페이지: 탭 스크롤 복원 ----
  const tabLinks = document.querySelectorAll('[data-bs-toggle="tab"]');
  tabLinks.forEach(function (tab) {
    tab.addEventListener('shown.bs.tab', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  // ---- 툴팁 초기화 ----
  const tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipEls.forEach(function (el) {
    new bootstrap.Tooltip(el);
  });

});
