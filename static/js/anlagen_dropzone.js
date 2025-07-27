// Modul zur Handhabung von Datei-Uploads direkt im Anlagen-Tab
import { getCookie } from './utils.js';

function initDropzone() {
    const dropzone = document.getElementById('anlage-dropzone');
    if (!dropzone) return;
    const input = dropzone.querySelector('input[type=file]');
    const uploadUrl = dropzone.dataset.uploadUrl;
    const anlageNr = dropzone.dataset.anlageNr;

    const sendFile = (file) => {
        const formData = new FormData();
        formData.append('upload', file);
        formData.append('anlage_nr', anlageNr);
        fetch(uploadUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken') || '',
                'HX-Request': 'true'
            }
        })
        .then(r => r.text())
        .then(html => {
            document.getElementById('anlage-tab-content').innerHTML = html;
        });
    };

    const handleFiles = (files) => {
        Array.from(files).forEach(sendFile);
        if (input) input.value = '';
    };

    dropzone.addEventListener('click', () => input && input.click());
    dropzone.addEventListener('dragover', e => {
        e.preventDefault();
        dropzone.classList.add('bg-gray-100');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-gray-100'));
    dropzone.addEventListener('drop', e => {
        e.preventDefault();
        dropzone.classList.remove('bg-gray-100');
        if (e.dataTransfer.files.length) {
            handleFiles(e.dataTransfer.files);
        }
    });
    if (input) {
        input.addEventListener('change', e => handleFiles(e.target.files));
    }
}

document.addEventListener('DOMContentLoaded', initDropzone);

// Bei HTMX-Austausch neu initialisieren
document.body.addEventListener('htmx:afterSwap', initDropzone);
