// JS für Farbmodus-Toggle
(function () {
    const storageKey = 'color-theme';
    const toggleBtn = document.getElementById('theme-toggle');
    const root = document.documentElement;

    function setTheme(theme) {
        if (theme === 'dark') {
            root.classList.add('dark');
            if (icon) {
                icon.classList.remove('fa-sun');
                icon.classList.add('fa-moon');
            }
        } else {
            root.classList.remove('dark');
            if (icon) {
                icon.classList.remove('fa-moon');
                icon.classList.add('fa-sun');
            }
        }
        try {
            localStorage.setItem(storageKey, theme);
        } catch (e) {
            // localStorage ist möglicherweise nicht verfügbar
        }
    }

    const icon = toggleBtn ? toggleBtn.querySelector('i') : null;

    function initTheme() {

        const stored = localStorage.getItem(storageKey);
        const theme = stored || (root.classList.contains('dark') ? 'dark' : 'light');
        setTheme(theme);

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
