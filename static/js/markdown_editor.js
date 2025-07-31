function initMarkdownEditor(idPrefix) {
    const view = document.getElementById(`${idPrefix}-view`);
    const textarea = document.getElementById(`${idPrefix}-textarea`);
    const editBtn = document.getElementById(`${idPrefix}-edit`);
    const saveBtn = document.getElementById(`${idPrefix}-save`);
    const cancelBtn = document.getElementById(`${idPrefix}-cancel`);
    if (!view || !textarea || !editBtn || !saveBtn || !cancelBtn) return;

    let editor = null;

    editBtn.addEventListener('click', () => {
        view.classList.add('hidden');
        textarea.classList.remove('hidden');
        editBtn.classList.add('hidden');
        saveBtn.classList.remove('hidden');
        cancelBtn.classList.remove('hidden');
        if (!editor) {
            editor = new EasyMDE({ element: textarea });
        }
    });

    cancelBtn.addEventListener('click', () => {
        if (editor) {
            editor.toTextArea();
            editor = null;
        }
        textarea.classList.add('hidden');
        view.classList.remove('hidden');
        editBtn.classList.remove('hidden');
        saveBtn.classList.add('hidden');
        cancelBtn.classList.add('hidden');
    });

    saveBtn.addEventListener('click', () => {
        if (editor) {
            textarea.value = editor.value();
        }
    });
}

window.initMarkdownEditor = initMarkdownEditor;
