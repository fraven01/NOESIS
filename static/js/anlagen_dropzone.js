// Aktiviert die Dropzone im Anlagen-Tab
function initDropzone() {
    const zone = document.getElementById('anlage-dropzone');
    const tableBody = document.getElementById('anlage-table-body');
    if (!zone || !tableBody || zone.dataset.initialized) return;
    zone.dataset.initialized = '1';

    const input = zone.querySelector('input[type=file]');
    const uploadUrl = zone.dataset.uploadUrl;
    const colspan = parseInt(zone.dataset.colspan || '6', 10);

    function setActiveTab(nr) {
        document.querySelectorAll('.anlage-tab-btn').forEach(btn => {
            if (btn.dataset.nr === String(nr)) {
                btn.classList.add('border-blue-600', 'text-blue-600');
                btn.classList.remove('border-transparent', 'text-gray-600');
            } else {
                btn.classList.remove('border-blue-600', 'text-blue-600');
                btn.classList.add('border-transparent', 'text-gray-600');
            }
        });
    }

    function uploadFile(file) {
        const rowId = 'upl-' + Math.random().toString(36).slice(2);
        const row = document.createElement('tr');
        row.id = rowId;
        row.innerHTML = `<td colspan="${colspan}"><span class="spinner"></span> ${file.name}</td>`;
        tableBody.prepend(row);

        const data = new FormData();
        data.append('upload', file);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', uploadUrl);
        xhr.setRequestHeader('HX-Request', 'true');
        const token = window.getCookie ? window.getCookie('csrftoken') : null;
        if (token) xhr.setRequestHeader('X-CSRFToken', token);
        xhr.onload = function () {
            const status = xhr.getResponseHeader('X-Upload-Status');
            if (xhr.status >= 200 && xhr.status < 300) {
                if (status === 'assigned') {
                    const nr = xhr.getResponseHeader('X-Anlage-Nr');
                    const container = document.getElementById('anlage-tab-content');
                    if (container) {
                        container.innerHTML = xhr.responseText;
                        if (nr) setActiveTab(nr);
                        if (window.htmx) htmx.process(container);
                    }
                } else if (status === 'manual') {
                    const target = document.getElementById(rowId);
                    if (target && window.htmx) {
                        htmx.swap(target, xhr.responseText, { swapStyle: 'outerHTML' });
                    }
                }
            } else {
                row.innerHTML = `<td colspan="${colspan}" class="text-red-600">Upload fehlgeschlagen</td>`;
            }
        };
        xhr.onerror = function () {
            row.innerHTML = `<td colspan="${colspan}" class="text-red-600">Upload fehlgeschlagen</td>`;
        };
        xhr.send(data);
    }

    function handleFiles(files) {
        Array.from(files).forEach(uploadFile);
        if (input) input.value = '';
    }

    zone.addEventListener('click', () => input && input.click());
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('bg-gray-100');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('bg-gray-100'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('bg-gray-100');
        if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    });
    if (input) input.addEventListener('change', (e) => handleFiles(e.target.files));
}

document.addEventListener('DOMContentLoaded', initDropzone);
document.body.addEventListener('htmx:afterSwap', initDropzone);
