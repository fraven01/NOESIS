// Aktiviert die Dropzone im Anlagen-Tab
function initDropzone() {
    const zone = document.getElementById('anlage-dropzone');
    const tableBody = document.getElementById('anlage-table-body');
    if (!zone || !tableBody) return;

    const input = zone.querySelector('input[type=file]');
    const uploadUrl = zone.dataset.uploadUrl;
    const anlageNr = zone.dataset.anlageNr;
    const colspan = parseInt(zone.dataset.colspan || '6', 10);

    function uploadFile(file) {
        const rowId = 'upl-' + Math.random().toString(36).slice(2);
        const row = document.createElement('tr');
        row.id = rowId;
        row.innerHTML = `<td colspan="${colspan}"><span class="spinner"></span> ${file.name}</td>`;
        tableBody.prepend(row);

        const data = new FormData();
        data.append('upload', file);
        if (anlageNr) data.append('anlage_nr', anlageNr);

        htmx.ajax('POST', uploadUrl, {
            target: '#' + rowId,
            swap: 'outerHTML',
            body: data
        });
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
