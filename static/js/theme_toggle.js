// JS für Farbmodus-Toggle
(function () {
    const storageKey = 'color-theme';
    const toggleBtn = document.getElementById('theme-toggle');
    const root = document.documentElement;

    function setTheme(theme) {
        if (theme === 'dark') {
            root.classList.add('dark');
        } else {
            root.classList.remove('dark');
        }
        localStorage.setItem(storageKey, theme);
    }

    function initTheme() {
        const stored = localStorage.getItem(storageKey);
        if (stored) {
            setTheme(stored);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        initTheme();
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                const isDark = root.classList.contains('dark');
                setTheme(isDark ? 'light' : 'dark');
            });
        }
    });
})();
