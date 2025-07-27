// Modul zur Aktivierung der Dropzone im Anlagen-Tab
import { getCookie } from './utils.js';

function initDropzone() {
    const dropzone = document.getElementById('anlage-dropzone');
    if (!dropzone) return;

    const input = dropzone.querySelector('input[type=file]');
    const uploadUrl = dropzone.dataset.uploadUrl;
    const anlageNr = dropzone.dataset.anlageNr;

    const tableBody = document.querySelector('#anlage-tab-content tbody');
    const colCount = document.querySelector('#anlage-tab-content thead tr')?.children.length || 1;

    const addPlaceholder = (file) => {
        const id = 'upload-' + Math.random().toString(36).slice(2, 9);
        const tr = document.createElement('tr');
        tr.id = id;
        tr.innerHTML = `<td colspan="${colCount}"><span class="spinner"></span> ${file.name}</td>`;
        if (tableBody) {
            tableBody.prepend(tr);
        }
        return id;
    };

    const sendFile = (file) => {
        const placeholderId = addPlaceholder(file);
        const values = { upload: file };
        if (anlageNr) values['anlage_nr'] = anlageNr;

        htmx.ajax('POST', uploadUrl, {
            target: '#' + placeholderId,
            swap: 'outerHTML',
            headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
            values: values
        });
    };

    const handleFiles = (files) => {
        Array.from(files).forEach(sendFile);
        if (input) input.value = '';
    };

    dropzone.addEventListener('click', () => input && input.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('bg-gray-100');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-gray-100'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('bg-gray-100');
        if (e.dataTransfer.files.length) {
            handleFiles(e.dataTransfer.files);
        }
    });

    if (input) {
        input.addEventListener('change', (e) => handleFiles(e.target.files));
    }
}

document.addEventListener('DOMContentLoaded', initDropzone);

// Bei HTMX-Austausch neu initialisieren
document.body.addEventListener('htmx:afterSwap', initDropzone);
