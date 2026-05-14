// 네이버 기자 분석기 - Main JS
// (Progress 폴링은 progress.html의 인라인 스크립트에서 처리)

document.addEventListener('DOMContentLoaded', function () {

  // ---- 테마 전환 ----
  const themeToggle = document.getElementById('themeToggle');
  const themeToggleIcon = document.getElementById('themeToggleIcon');
  const themeToggleLabel = document.getElementById('themeToggleLabel');

  function getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'black' ? 'black' : 'white';
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem('naverJournalistAnalyzerTheme', theme);
    } catch (e) {
      // localStorage를 사용할 수 없는 환경에서는 현재 페이지에만 적용한다.
    }
  }

  function updateThemeControl(theme) {
    if (!themeToggle) return;

    const isBlack = theme === 'black';
    const nextThemeLabel = isBlack ? '화이트' : '블랙';
    const title = `${nextThemeLabel} 테마로 변경`;

    themeToggle.setAttribute('aria-label', title);
    themeToggle.setAttribute('aria-pressed', String(isBlack));
    themeToggle.setAttribute('data-bs-title', title);
    themeToggle.setAttribute('title', title);

    if (themeToggleIcon) {
      themeToggleIcon.className = isBlack ? 'bi bi-sun me-1' : 'bi bi-moon-stars me-1';
    }

    if (themeToggleLabel) {
      themeToggleLabel.textContent = nextThemeLabel;
    }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    saveTheme(theme);
    updateThemeControl(theme);
  }

  applyTheme(getCurrentTheme());

  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      const nextTheme = getCurrentTheme() === 'black' ? 'white' : 'black';
      applyTheme(nextTheme);

      const tooltip = bootstrap.Tooltip.getInstance(themeToggle);
      if (tooltip) {
        tooltip.setContent({ '.tooltip-inner': themeToggle.getAttribute('title') });
      }
    });
  }

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
