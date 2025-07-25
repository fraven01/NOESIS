// JavaScript-Modul für Dateiupload mit Vorschau und Fortschrittsanzeige
(function(){
    const acceptedImageTypes = ['image/jpeg','image/png','image/gif'];
    const acceptedPdfTypes = ['application/pdf'];
    const acceptedDocxTypes = ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    const maxSize = 10 * 1024 * 1024; // 10MB

    function loadScript(url){
        return new Promise((resolve, reject) => {
            if(document.querySelector(`script[src="${url}"]`)) return resolve();
            const s = document.createElement('script');
            s.src = url;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    function createPreview(file){
        const container = document.getElementById('preview-container');
        if(!container) return null;
        const wrapper = document.createElement('div');
        wrapper.className = 'preview-item flex flex-col mb-2';
        const thumb = document.createElement('div');
        thumb.className = 'preview-thumb mb-1';

        if(acceptedImageTypes.includes(file.type)){
            const img = document.createElement('img');
            img.className = 'preview-img h-24 object-contain';
            const reader = new FileReader();
            reader.onload = e => img.src = e.target.result;
            reader.readAsDataURL(file);
            thumb.appendChild(img);
        } else if(acceptedPdfTypes.includes(file.type)){
            const canvas = document.createElement('canvas');
            canvas.className = 'preview-pdf h-24';
            thumb.appendChild(canvas);
            loadScript('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.9.179/pdf.min.js').then(() => {
                if(window['pdfjsLib']){
                    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.9.179/pdf.worker.min.js';
                    pdfjsLib.getDocument({data:file}).promise.then(pdf => pdf.getPage(1)).then(page => {
                        const vp = page.getViewport({scale:1});
                        canvas.height = vp.height;
                        canvas.width = vp.width;
                        page.render({canvasContext: canvas.getContext('2d'), viewport: vp});
                    });
                }
            }).catch(()=>{});
        } else if(acceptedDocxTypes.includes(file.type)){
            const docDiv = document.createElement('div');
            docDiv.className = 'preview-docx';
            thumb.appendChild(docDiv);
            loadScript('https://cdn.jsdelivr.net/npm/docx-preview@0.4.1/dist/docx-preview.min.js').then(() => {
                if(window['docx']){
                    docx.renderAsync(file, docDiv).catch(()=>{});
                }
            }).catch(()=>{});
        } else {
            const span = document.createElement('span');
            span.textContent = file.name;
            thumb.appendChild(span);
        }

        const barContainer = document.createElement('div');
        barContainer.className = 'progress-container bg-gray-200 rounded h-2 w-full';
        const bar = document.createElement('div');
        bar.className = 'progress-bar bg-blue-600 h-2 rounded';
        bar.style.width = '0%';
        barContainer.appendChild(bar);

        wrapper.appendChild(thumb);
        wrapper.appendChild(barContainer);
        container.appendChild(wrapper);
        return bar;
    }

    function validateFile(file){
        if(file.size > maxSize){
            return 'Datei zu groß: ' + file.name;
        }
        const allowed = [...acceptedImageTypes, ...acceptedPdfTypes, ...acceptedDocxTypes];
        if(!allowed.includes(file.type)){
            return 'Ungültiger Dateityp: ' + file.name;
        }
        return null;
    }

    function sendFile(form, file, bar){
        return new Promise((resolve, reject) => {
            const url = form.getAttribute('hx-post') || form.action;
            const formData = new FormData(form);
            formData.set('upload', file);
            const xhr = new XMLHttpRequest();
            xhr.open('POST', url);
            const token = window.getCookie ? window.getCookie('csrftoken') : null;
            if(token) xhr.setRequestHeader('X-CSRFToken', token);
            xhr.setRequestHeader('HX-Request', 'true');
            xhr.upload.addEventListener('progress', (e) => {
                if(e.lengthComputable){
                    const percent = (e.loaded / e.total) * 100;
                    bar.style.width = percent + '%';
                }
            });
            xhr.addEventListener('load', () => {
                bar.style.width = '100%';
                if(xhr.status >= 200 && xhr.status < 300){
                    resolve(xhr.responseText);
                } else {
                    reject(xhr.responseText || 'Fehler');
                }
            });
            xhr.addEventListener('error', () => reject('Netzwerkfehler'));
            xhr.send(formData);
        });
    }

    function initFileUpload(){
        const input = document.getElementById('id_upload');
        const dropzone = document.getElementById('dropzone');
        const form = input ? input.closest('form') : null;
        const container = document.getElementById('preview-container');
        if(!input || !dropzone || !form || !container) return;

        let currentFiles = [];
        function handle(files){
            container.innerHTML = '';
            currentFiles = [];
            for(const file of files){
                const err = validateFile(file);
                if(err){
                    const d = document.createElement('div');
                    d.className = 'text-red-600';
                    d.textContent = err;
                    container.appendChild(d);
                    continue;
                }
                const bar = createPreview(file);
                currentFiles.push({file, bar});
            }
        }

        input.addEventListener('change', e => handle(e.target.files));
        dropzone.addEventListener('click', () => input.click());
        dropzone.addEventListener('dragover', e => {e.preventDefault(); dropzone.classList.add('bg-gray-100');});
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-gray-100'));
        dropzone.addEventListener('drop', e => {
            e.preventDefault();
            dropzone.classList.remove('bg-gray-100');
            input.files = e.dataTransfer.files;
            handle(e.dataTransfer.files);
        });

        form.addEventListener('submit', async function(ev){
            ev.preventDefault();
            if(currentFiles.length === 0){
                form.submit();
                return;
            }
            const targetSel = form.getAttribute('hx-target');
            const swap = form.getAttribute('hx-swap') || 'innerHTML';
            const target = document.querySelector(targetSel);
            for(const item of currentFiles){
                try {
                    const resp = await sendFile(form, item.file, item.bar);
                    if(target && swap === 'innerHTML'){
                        target.innerHTML = resp;
                        if(window.htmx){ htmx.process(target); }
                    }
                } catch(e){
                    const errDiv = document.createElement('div');
                    errDiv.className = 'text-red-600';
                    errDiv.textContent = e;
                    container.appendChild(errDiv);
                }
            }
        });
    }

    window.initFileUpload = initFileUpload;
})();

