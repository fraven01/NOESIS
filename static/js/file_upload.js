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
        const m = name.toLowerCase().match(/anlage_(\d)/);
        return m ? parseInt(m[1], 10) : null;
    }

    // --- Kombinierte Validierungslogik ---
    function validateFile(file, anlageNrDropdown) {
        const nrDropdown = anlageNrDropdown ? parseInt(anlageNrDropdown.value, 10) : null;
        const nrFilename = getAnlageNrFromName(file.name);
        const anlageNr = nrFilename !== null ? nrFilename : nrDropdown;

        if (nrFilename === null) {
            return 'Dateiname muss dem Muster anlage_[1-6] entsprechen.';
        }
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
    function createPreview(file, container, onRemove) {
        const wrapper = document.createElement('div');
        wrapper.className = 'preview-item flex flex-col mb-2 border p-2 rounded';
        const thumb = document.createElement('div');
        thumb.className = 'preview-thumb mb-1 text-center';

        const fileNameSpan = document.createElement('span');
        fileNameSpan.className = "font-bold text-sm mb-2 block";
        fileNameSpan.textContent = file.name;

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'self-end text-gray-500 hover:text-red-600';
        removeBtn.textContent = '✖';
        removeBtn.addEventListener('click', () => {
            wrapper.remove();
            if (typeof onRemove === 'function') onRemove();
        });

        wrapper.appendChild(removeBtn);
        wrapper.appendChild(fileNameSpan);
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
             // DOCX-Vorschau (vereinfacht)
            thumb.textContent = '📄 DOCX Vorschau';
        }

        const barContainer = document.createElement('div');
        barContainer.className = 'progress-container bg-gray-200 rounded h-2 w-full mt-2';
        const bar = document.createElement('div');
        bar.className = 'progress-bar bg-blue-600 h-2 rounded';
        bar.style.width = '0%';
        barContainer.appendChild(bar);
        wrapper.appendChild(barContainer);

        return { bar, wrapper };
    }
    
    // --- Logik zum Senden der Datei aus 'main' ---
    function sendFile(form, file, bar) {
        return new Promise((resolve, reject) => {
             const url = form.getAttribute('hx-post') || form.action;
             const formData = new FormData(form);
             formData.set('upload', file); // 'upload' anpassen, falls nötig
             const xhr = new XMLHttpRequest();
             xhr.open('POST', url, true);

             const token = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value;
             if (token) xhr.setRequestHeader('X-CSRFToken', token);
             xhr.setRequestHeader('HX-Request', 'true');

             xhr.upload.addEventListener('progress', e => {
                 if (e.lengthComputable) {
                     const percent = (e.loaded / e.total) * 100;
                     bar.style.width = percent + '%';
                 }
             });
             xhr.addEventListener('load', () => {
                 bar.style.width = '100%';
                 if (xhr.status >= 200 && xhr.status < 300) {
                     resolve(xhr.responseText);
                 } else {
                     reject(xhr.responseText || 'Upload-Fehler');
                 }
             });
             xhr.addEventListener('error', () => reject('Netzwerkfehler'));
             xhr.send(formData);
        });
    }


    // --- Haupt-Initialisierungsfunktion ---
    function initFileUpload() {
        const input = document.getElementById('id_upload');
        const dropzone = document.getElementById('dropzone');
        const form = input ? input.closest('form') : null;
        const container = document.getElementById('preview-container');
        const anlageSelect = document.getElementById('id_anlage_nr');

        if (!input || !dropzone || !form || !container) return;

        let currentFiles = [];

        function updateDuplicateStatus() {
            const counts = {};
            let hasDuplicate = false;

            for (const item of currentFiles) {
                counts[item.anlageNr] = (counts[item.anlageNr] || 0) + 1;
            }

            for (const item of currentFiles) {
                item.wrapper.classList.remove('duplicate');
                if (counts[item.anlageNr] > 1) {
                    item.wrapper.classList.add('duplicate');
                    hasDuplicate = true;
                }
            }

            let warning = document.getElementById('duplicate-warning');
            if (hasDuplicate) {
                if (!warning) {
                    warning = document.createElement('div');
                    warning.id = 'duplicate-warning';
                    warning.className = 'text-red-600 p-2 border border-red-400 rounded mb-2';
                    warning.textContent = 'Mehrere Dateien f\u00fcr dieselbe Anlage ausgew\u00e4hlt.';
                    container.insertBefore(warning, container.firstChild);
                }
            } else if (warning) {
                warning.remove();
            }

            const submitButton = form.querySelector('[type=submit]');
            if (submitButton) submitButton.disabled = hasDuplicate;
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
                const preview = createPreview(file, container, () => {
                    const idx = currentFiles.findIndex(it => it.file === file);
                    if (idx !== -1) currentFiles.splice(idx, 1);
                    updateDuplicateStatus();
                });
                const anlageNr = getAnlageNrFromName(file.name);
                currentFiles.push({ file, bar: preview.bar, wrapper: preview.wrapper, anlageNr });
            }

            updateDuplicateStatus();
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

        form.addEventListener('submit', async function(ev) {
            ev.preventDefault();
            if (currentFiles.length === 0) {
                 // Ggf. eine Meldung anzeigen, dass keine Datei gewählt wurde.
                return;
            }
            
            const submitButton = form.querySelector('[type=submit]');
            if(submitButton) submitButton.disabled = true;

            const targetSel = form.getAttribute('hx-target');
            const target = targetSel ? document.querySelector(targetSel) : null;

            for (const item of currentFiles) {
                try {
                    const resp = await sendFile(form, item.file, item.bar);
                    if (target) {
                        target.innerHTML = resp;
                        if (window.htmx) { htmx.process(target); }
                    } else {
                        // Fallback, wenn kein htmx-Target da ist, z.B. Seite neu laden
                        window.location.reload();
                    }
                } catch (e) {
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'text-red-600 mt-2 p-2 border border-red-400 rounded';
                    errorDiv.textContent = `Fehler: ${e}`;
                    item.bar.parentElement.appendChild(errorDiv);
                    if(submitButton) submitButton.disabled = false;
                }
            }
        });
    }

    document.addEventListener('DOMContentLoaded', initFileUpload);
})();