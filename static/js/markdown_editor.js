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

    editBtn.addEventListener('click', () => {
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
