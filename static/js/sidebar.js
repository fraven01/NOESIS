/**
 * JS für Seitenleisten-Toggle mit mobilem Off-Canvas.
 */
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
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

    const accordionKey = 'sidebar-accordion';
    const accordionButtons = sidebar.querySelectorAll('.sidebar-accordion-btn');

    try {
        const activeAccordion = localStorage.getItem(accordionKey);
        if (activeAccordion) {
            const activeList = document.getElementById(activeAccordion);
            const activeBtn = sidebar.querySelector(`.sidebar-accordion-btn[data-accordion-target="${activeAccordion}"]`);
            if (activeList && activeBtn) {
                activeList.classList.remove('hidden');
                const icon = activeBtn.querySelector('i');
                if (icon) {
                    icon.classList.add('rotate-180');
                }
            }
        }
    } catch (e) {
        // localStorage ist möglicherweise nicht verfügbar
    }

    accordionButtons.forEach((btn) => {
        const targetId = btn.getAttribute('data-accordion-target');
        const target = document.getElementById(targetId);
        if (!target) {
            return;
        }
        btn.addEventListener('click', () => {
            const hidden = target.classList.toggle('hidden');
            const icon = btn.querySelector('i');
            if (icon) {
                icon.classList.toggle('rotate-180');
            }
            try {
                localStorage.setItem(accordionKey, hidden ? '' : targetId);
            } catch (e) {
                // localStorage ist möglicherweise nicht verfügbar
            }
        });
    });
});
