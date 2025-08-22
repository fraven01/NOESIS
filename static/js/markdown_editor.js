// Hilfsfunktionen zum Laden der EasyMDE-Ressourcen
let easymdeLoader = null;

function loadEasyMDE() {
    if (window.EasyMDE || (window.customElements && customElements.get('mce-autosize-textarea'))) {
        return Promise.resolve();
    }
    if (!easymdeLoader) {
        easymdeLoader = new Promise((resolve, reject) => {
            const cssId = 'easymde-css';
            if (!document.getElementById(cssId)) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = 'https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.css';
                link.id = cssId;
                const firstStylesheet = document.head.querySelector('link[rel="stylesheet"]');
                if (firstStylesheet) {
                    document.head.insertBefore(link, firstStylesheet);
                } else {
                    document.head.appendChild(link);
                }
            }
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    return easymdeLoader;
}

function initMarkdownEditor(idPrefix) {
    const view = document.getElementById(`${idPrefix}-view`);
    const textarea = document.getElementById(`${idPrefix}-textarea`);
    const editBtn = document.getElementById(`${idPrefix}-edit`);
    const saveBtn = document.getElementById(`${idPrefix}-save`);
    const cancelBtn = document.getElementById(`${idPrefix}-cancel`);
    if (!view || !textarea || !editBtn || !saveBtn || !cancelBtn) return;

    // Mehrfache Initialisierung vermeiden
    if (textarea.dataset.editorInitialized) {
        return;
    }
    textarea.dataset.editorInitialized = "true";

    editBtn.addEventListener('click', async () => {
        await loadEasyMDE();
        view.classList.add('hidden');
        textarea.classList.remove('hidden');
        editBtn.classList.add('hidden');
        saveBtn.classList.remove('hidden');
        cancelBtn.classList.remove('hidden');
        if (!textarea._markdownEditor) {
            textarea._markdownEditor = new EasyMDE({ element: textarea });
        }
    });

    cancelBtn.addEventListener('click', () => {
        const editor = textarea._markdownEditor;
        if (editor) {
            editor.toTextArea();
            textarea._markdownEditor = null;
        }
        textarea.classList.add('hidden');
        view.classList.remove('hidden');
        editBtn.classList.remove('hidden');
        saveBtn.classList.add('hidden');
        cancelBtn.classList.add('hidden');
    });

    saveBtn.addEventListener('click', () => {
        const editor = textarea._markdownEditor;
        if (editor) {
            textarea.value = editor.value();
        }
    });
}

window.initMarkdownEditor = initMarkdownEditor;
