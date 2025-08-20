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
        try {
            localStorage.setItem(storageKey, theme);
        } catch (e) {
            // localStorage ist möglicherweise nicht verfügbar
        }
    }

    function initTheme() {
        if (root.classList.contains('dark')) {
            return;
        }
        try {
            const stored = localStorage.getItem(storageKey);
            if (stored === 'dark') {
                root.classList.add('dark');
            }
        } catch (e) {
            // localStorage ist möglicherweise nicht verfügbar
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
