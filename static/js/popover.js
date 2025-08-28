(function () {
  function removeAll() {
    document.querySelectorAll('.custom-popover').forEach(el => el.remove());
  }
  function createPopover(content, target) {
    removeAll();
    const pop = document.createElement('div');
    // Dark-Mode-kompatible Popover-Stile
    pop.className = [
      'custom-popover',
      'absolute',
      // Hintergrund + Rahmen (Hell/Dunkel)
      'bg-white', 'dark:bg-gray-800',
      'border', 'border-gray-300', 'dark:border-gray-600',
      // Textfarben (Hell/Dunkel)
      'text-gray-900', 'dark:text-gray-100',
      // Layout
      'px-2', 'py-1', 'rounded', 'shadow', 'text-sm',
      'max-w-[250px]', 'whitespace-normal', 'z-[1000]'
    ].join(' ');
    pop.innerHTML = (content || '').replace(/\n/g, '<br>');
    document.body.appendChild(pop);
    const rect = target.getBoundingClientRect();
    pop.style.left = rect.right + window.scrollX + 8 + 'px';
    pop.style.top  = rect.top  + window.scrollY + 'px';
    return pop;
  }
  function attach(el) {
    let inst = null;
    el.addEventListener('mouseenter', () => {
      const html = el.dataset.popoverContent;
      if (html) inst = createPopover(html, el);
    });
    el.addEventListener('mouseleave', () => {
      if (inst) { inst.remove(); inst = null; }
    });
  }
  window.attachCustomPopover = attach;
  window.initCustomPopovers = function (root = document) {
    root.querySelectorAll('[data-popover-content]').forEach(el => {
      if (!el.dataset.popoverInit) {
        attach(el);
        el.dataset.popoverInit = '1';
      }
    });
  };
  document.body.addEventListener('htmx:beforeSwap', removeAll);
  document.addEventListener('DOMContentLoaded', () => initCustomPopovers());
})();
