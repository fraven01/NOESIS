/**
 * JS für Seitenleisten-Toggle mit mobilem Off-Canvas.
 */
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
    const overlay = document.getElementById('sidebar-overlay');
    const storageKey = 'sidebar-open';
    const accordionKey = 'sidebar-active-accordion';

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

    const openAccordion = (id, store = true) => {
        const btn = sidebar.querySelector(`.sidebar-accordion-btn[data-accordion-target="${id}"]`);
        const target = document.getElementById(id);
        if (!btn || !target) {
            return;
        }
        target.classList.remove('hidden');
        const icon = btn.querySelector('i');
        if (icon) {
            icon.classList.add('rotate-180');
        }
        if (store) {
            try {
                localStorage.setItem(accordionKey, id);
            } catch (e) {
                // localStorage ist möglicherweise nicht verfügbar
            }
        }
    };

    const closeAccordion = (id) => {
        const btn = sidebar.querySelector(`.sidebar-accordion-btn[data-accordion-target="${id}"]`);
        const target = document.getElementById(id);
        if (!btn || !target) {
            return;
        }
        target.classList.add('hidden');
        const icon = btn.querySelector('i');
        if (icon) {
            icon.classList.remove('rotate-180');
        }
        try {
            localStorage.removeItem(accordionKey);
        } catch (e) {
            // localStorage ist möglicherweise nicht verfügbar
        }
    };

    let activeAcc = null;
    try {
        activeAcc = localStorage.getItem(accordionKey);
    } catch (e) {
        // localStorage ist möglicherweise nicht verfügbar
    }

    if (activeAcc) {
        openAccordion(activeAcc, false);
    } else {
        const activeLink = sidebar.querySelector('.active-nav-link');
        if (activeLink) {
            const parent = activeLink.closest('ul');
            if (parent && parent.id) {
                openAccordion(parent.id);
            }
        }
    }

    const accordionButtons = sidebar.querySelectorAll('.sidebar-accordion-btn');
    accordionButtons.forEach((btn) => {
        const targetId = btn.getAttribute('data-accordion-target');
        const target = document.getElementById(targetId);
        if (!target) {
            return;
        }
        btn.addEventListener('click', () => {
            const isHidden = target.classList.contains('hidden');
            if (isHidden) {
                openAccordion(targetId);
            } else {
                closeAccordion(targetId);
            }
        });
    });

    const navLinks = sidebar.querySelectorAll('nav a');
    navLinks.forEach((link) => {
        link.addEventListener('click', () => {
            const parent = link.closest('ul');
            if (parent && parent.id) {
                try {
                    localStorage.setItem(accordionKey, parent.id);
                } catch (e) {
                    // localStorage ist möglicherweise nicht verfügbar
                }
            }
        });
    });
});
