/**
 * JS für Seitenleisten-Toggle mit mobilem Off-Canvas.
 */
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('menu-toggle');
    const overlay = document.getElementById('sidebar-overlay');
    const storageKey = 'sidebar-open';

    if (!sidebar) {
        return;
    }

    const setSidebar = (open) => {
        if (open) {
            sidebar.classList.add('translate-x-0');
            sidebar.classList.remove('-translate-x-full', 'md:-translate-x-full');
            if (overlay) {
                overlay.classList.add('sidebar-overlay-active');
            }
        } else {
            sidebar.classList.remove('translate-x-0');
            sidebar.classList.add('-translate-x-full', 'md:-translate-x-full');
            if (overlay) {
                overlay.classList.remove('sidebar-overlay-active');
            }
        }
        try {
            localStorage.setItem(storageKey, open ? '1' : '0');
        } catch (e) {
            // localStorage ist möglicherweise nicht verfügbar
        }
    };

    let open = window.innerWidth >= 768;
    try {
        const stored = localStorage.getItem(storageKey);
        if (stored !== null) {
            open = stored === '1';
        }
    } catch (e) {
        // localStorage ist möglicherweise nicht verfügbar
    }
    setSidebar(open);

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isClosed = sidebar.classList.contains('-translate-x-full');
            setSidebar(isClosed);
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => setSidebar(false));
    }
});
