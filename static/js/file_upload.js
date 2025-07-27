(function() {
    // --- Konfiguration aus dem 'main'-Branch ---
    const acceptedPdfTypes = ['application/pdf'];
    const acceptedDocxTypes = ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'];
    const maxSize = window.MAX_UPLOAD_SIZE || 10 * 1024 * 1024; // 10MB als Standard

    // --- Hilfsfunktionen aus beiden Branches kombiniert ---
    function loadScript(url) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${url}"]`)) return resolve();
            const s = document.createElement('script');
            s.src = url;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    function getAnlageNrFromName(name) {
        const m = name.toLowerCase().match(/anlage[\s_-]?(\d)/i);
        return m ? parseInt(m[1], 10) : null;
    }

    // --- Kombinierte Validierungslogik ---
    function validateFile(file, anlageNrDropdown) {
        const nrDropdown = anlageNrDropdown ? parseInt(anlageNrDropdown.value, 10) : null;
        const nrFilename = getAnlageNrFromName(file.name);
        const anlageNr = nrFilename !== null ? nrFilename : nrDropdown;
        if (maxSize && file.size > maxSize) {
            const mb = Math.round(maxSize / 1024 / 1024);
            return `Datei zu groß (max. ${mb} MB).`;
        }
        
        const ext = file.name.split('.').pop().toLowerCase();
        const fileType = file.type;

        if (anlageNr === 3) {
            if (!(['docx', 'pdf'].includes(ext) && (acceptedDocxTypes.includes(fileType) || acceptedPdfTypes.includes(fileType)))) {
                 return 'Nur .docx oder .pdf erlaubt für Anlage 3.';
            }
        } else {
            if (!(['docx'].includes(ext) && acceptedDocxTypes.includes(fileType))) {
                return 'Nur .docx Dateien erlaubt.';
            }
        }
        
        // Anlage-Nr im Dropdown automatisch setzen
        if (anlageNrDropdown && !nrDropdown && nrFilename) {
            anlageNrDropdown.value = nrFilename;
        }

        return null; // Kein Fehler
    }

    // --- Vorschau-Logik aus 'main' ---
    function createPreview(file, container, onRemove, anlageNr) {
        const wrapper = document.createElement('div');
        wrapper.className = 'preview-item flex flex-col mb-2 border p-2 rounded';
        const thumb = document.createElement('div');
        thumb.className = 'preview-thumb mb-1 text-center';

        const fileNameSpan = document.createElement('span');
        fileNameSpan.className = "font-bold text-sm mb-2 block";
        fileNameSpan.textContent = file.name;

        const select = document.createElement('select');
        select.className = 'anlage-select ml-2 border rounded p-1';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '-';
        select.appendChild(placeholder);
        for (let i = 1; i <= 6; i++) {
            const opt = document.createElement('option');
            opt.value = String(i);
            opt.textContent = String(i);
            select.appendChild(opt);
        }
        if (anlageNr) {
            select.value = String(anlageNr);
        } else {
            select.value = '';
        }

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'self-end text-gray-500 hover:text-red-600';
        removeBtn.textContent = '✖';
        removeBtn.addEventListener('click', () => {
            wrapper.remove();
            if (typeof onRemove === 'function') onRemove();
        });

        wrapper.appendChild(removeBtn);
        const nameWrapper = document.createElement('div');
        nameWrapper.className = 'flex items-center mb-1';
        nameWrapper.appendChild(fileNameSpan);
        nameWrapper.appendChild(select);
        wrapper.appendChild(nameWrapper);
        wrapper.appendChild(thumb);
        container.appendChild(wrapper);

        // Thumbnail-Erzeugung
        if (file.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.className = 'preview-img h-24 object-contain mx-auto';
            const reader = new FileReader();
            reader.onload = e => img.src = e.target.result;
            reader.readAsDataURL(file);
            thumb.appendChild(img);
        } else if (acceptedPdfTypes.includes(file.type)) {
            // PDF-Vorschau (vereinfacht, da komplex)
            thumb.textContent = '📄 PDF Vorschau';
        } else if (acceptedDocxTypes.includes(file.type)) {
            const docxContainer = document.createElement('div');
            docxContainer.className = 'preview-docx flex items-center justify-center';
            docxContainer.innerHTML = '<span class="spinner"></span> wird geladen...';
            thumb.appendChild(docxContainer);

            const token = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value;
            const formData = new FormData();
            formData.append('docx', file);
            fetch(window.DOCX_PREVIEW_URL, {
                method: 'POST',
                headers: token ? { 'X-CSRFToken': token } : {},
                body: formData
            })
                .then(r => r.json())
                .then(data => {
                    docxContainer.innerHTML = data.html || 'Keine Vorschau verfügbar';
                })
                .catch(() => {
                    docxContainer.textContent = 'Vorschau konnte nicht geladen werden';
                });
        }

        const barContainer = document.createElement('div');
        barContainer.className = 'progress-container bg-gray-200 rounded h-2 w-full mt-2';
        const bar = document.createElement('div');
        bar.className = 'progress-bar bg-blue-600 h-2 rounded';
        bar.style.width = '0%';
        barContainer.appendChild(bar);
        wrapper.appendChild(barContainer);

        return { bar, wrapper, select };
    }
    
    // --- Upload-Logik entfernt. HTMX übernimmt den Dateiupload ---


    // --- Haupt-Initialisierungsfunktion ---
    function initFileUpload() {
        const input = document.getElementById('id_upload');
        const dropzone = document.getElementById('dropzone');
        const form = input ? input.closest('form') : null;
        const container = document.getElementById('preview-container');
        const anlageSelect = document.getElementById('id_anlage_nr');
        const submitButton = form ? form.querySelector('[type=submit]') : null;

        const uploadUrl = form ? (form.getAttribute('hx-post') || form.action) : '';
        const projMatch = uploadUrl.match(/projekte\/(\d+)\//);
        const projectId = projMatch ? projMatch[1] : null;

        // Warnungselement für doppelte Anlagennummern
        const dupWarning = document.createElement('div');
        dupWarning.className = 'text-red-600 p-2 border border-red-400 rounded mb-2 hidden';
        dupWarning.textContent = 'Mehrere Dateien besitzen dieselbe Anlage-Nummer.';
        container.parentNode.insertBefore(dupWarning, container);

        if (!input || !dropzone || !form || !container) return;

        let currentFiles = [];

        // Prüft auf fehlende oder doppelte Anlagennummern und aktualisiert UI
        function checkDuplicates() {
            const counts = {};
            let hasMissing = false;
            currentFiles.forEach(it => {
                if (it.anlageNr) {
                    counts[it.anlageNr] = (counts[it.anlageNr] || 0) + 1;
                } else {
                    hasMissing = true;
                }
            });

            let hasDup = false;
            currentFiles.forEach(it => {
                if (it.anlageNr && counts[it.anlageNr] > 1) {
                    it.wrapper.classList.add('border-red-600');
                    hasDup = true;
                } else if (!it.anlageNr) {
                    it.wrapper.classList.add('border-red-600');
                } else {
                    it.wrapper.classList.remove('border-red-600');
                }
            });

            if (hasDup || hasMissing) {
                dupWarning.classList.remove('hidden');
                dupWarning.textContent = hasMissing
                    ? 'Bitte jeder Datei eine eindeutige Nummer zuweisen.'
                    : 'Mehrere Dateien besitzen dieselbe Anlage-Nummer.';
                // Der Submit-Button bleibt aktiv, Nutzer wird nur gewarnt
                // if (submitButton) submitButton.disabled = true;
            } else {
                dupWarning.classList.add('hidden');
                // if (submitButton) submitButton.disabled = false;
            }
        }

        function handleFiles(files) {
            container.innerHTML = ''; // Alte Vorschauen löschen
            currentFiles = [];
            
            for (const file of files) {
                const error = validateFile(file, anlageSelect);
                if (error) {
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'text-red-600 p-2 border border-red-400 rounded';
                    errorDiv.textContent = error;
                    container.appendChild(errorDiv);
                    input.value = ''; // Input zurücksetzen bei Fehler
                    return; // Stoppt bei erstem Fehler
                }
                const detectedNr = getAnlageNrFromName(file.name);
                const preview = createPreview(file, container, () => {
                    const idx = currentFiles.findIndex(it => it.file === file);
                    if (idx !== -1) currentFiles.splice(idx, 1);
                    checkDuplicates();
                }, detectedNr);
                const item = { file, bar: preview.bar, wrapper: preview.wrapper, select: preview.select, anlageNr: detectedNr };
                currentFiles.push(item);
                preview.select.addEventListener('change', () => {
                    const val = parseInt(preview.select.value, 10);
                    item.anlageNr = isNaN(val) ? null : val;
                    checkDuplicates();
                });
            }
            checkDuplicates();
        }

        dropzone.addEventListener('click', () => input.click());
        dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('bg-gray-100'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-gray-100'));
        dropzone.addEventListener('drop', e => {
            e.preventDefault();
            dropzone.classList.remove('bg-gray-100');
            if (e.dataTransfer.files.length > 0) {
                input.files = e.dataTransfer.files;
                handleFiles(e.dataTransfer.files);
            }
        });
        input.addEventListener('change', e => handleFiles(e.target.files));

        // HTMX sendet das Formular. Eigene Upload-Logik ist nicht mehr nötig.
    }

    document.addEventListener('DOMContentLoaded', initFileUpload);
})();