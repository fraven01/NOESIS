(function(){
    function createPopover(content, target){
        const pop = document.createElement('div');
        pop.className = 'custom-popover';
        pop.innerHTML = (content || '').replace(/\n/g, '<br>');
        document.body.appendChild(pop);
        const rect = target.getBoundingClientRect();
        pop.style.left = rect.right + window.scrollX + 8 + 'px';
        pop.style.top = rect.top + window.scrollY + 'px';
        return pop;
    }
    function attach(el){
        let instance = null;
        el.addEventListener('mouseenter', () => {
            const html = el.dataset.popoverContent;
            if(html){
                instance = createPopover(html, el);
            }
        });
        el.addEventListener('mouseleave', () => {
            if(instance){
                instance.remove();
                instance = null;
            }
        });
    }
    window.attachCustomPopover = attach;
    window.initCustomPopovers = function(container=document){
        container.querySelectorAll('[data-popover-content]').forEach(el => {
            if(!el.dataset.popoverInit){
                attach(el);
                el.dataset.popoverInit = '1';
            }
        });
    };
})();
