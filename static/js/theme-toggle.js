(function () {
  const storageKey = "pr-module-theme";

  function normalize(theme) {
    return theme === "white" ? "white" : "black";
  }

  function currentTheme() {
    return normalize(document.documentElement.dataset.theme || localStorage.getItem(storageKey));
  }

  function applyTheme(theme) {
    const nextTheme = normalize(theme);
    document.documentElement.dataset.theme = nextTheme;
    localStorage.setItem(storageKey, nextTheme);

    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const isWhite = nextTheme === "white";
      button.textContent = isWhite ? "◐ 블랙" : "☼ 화이트";
      button.setAttribute("aria-label", isWhite ? "블랙 테마로 전환" : "화이트 테마로 전환");
      button.setAttribute("aria-pressed", String(isWhite));
    });
  }

  applyTheme(currentTheme());

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        applyTheme(currentTheme() === "white" ? "black" : "white");
      });
    });
  });
})();
