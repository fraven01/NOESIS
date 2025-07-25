(function(){
    function init(){
        const dropzone = document.getElementById('dropzone');
        const input = document.getElementById('id_upload');
        const select = document.getElementById('id_anlage_nr');
        if(!dropzone || !input) return;
        let msg = document.getElementById('dropzone-msg');
        if(!msg){
            msg = document.createElement('div');
            msg.id = 'dropzone-msg';
            msg.className = 'text-red-600 mt-2';
            dropzone.insertAdjacentElement('afterend', msg);
        }
        function showMessage(text){
            msg.textContent = text || '';
        }
        function getAnlageNrFromName(name){
            const m = name.toLowerCase().match(/anlage_(\d)/);
            return m ? parseInt(m[1],10) : null;
        }
        function checkFile(file){
            const max = window.MAX_UPLOAD_SIZE || 0;
            const nrSel = select ? parseInt(select.value,10) : null;
            const nrName = getAnlageNrFromName(file.name);
            const nr = nrSel || nrName;
            if(nrName===null){
                showMessage('Dateiname muss dem Muster anlage_[1-6] entsprechen');
                return false;
            }
            if(max && file.size > max){
                const mb = Math.round(max/1024/1024);
                showMessage(`Datei zu groß (max. ${mb} MB)`);
                return false;
            }
            const ext = file.name.split('.').pop().toLowerCase();
            if(nr===3){
                if(!['docx','pdf'].includes(ext)){
                    showMessage('Nur .docx oder .pdf erlaubt für Anlage 3');
                    return false;
                }
            }else if(ext !== 'docx'){
                showMessage('Nur .docx Dateien erlaubt');
                return false;
            }
            if(select && !nrSel && nrName){
                select.value = nrName;
            }
            showMessage('');
            return true;
        }
        dropzone.addEventListener('click', () => input.click());
        dropzone.addEventListener('dragover', e => {e.preventDefault(); dropzone.classList.add('bg-gray-100');});
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-gray-100'));
        dropzone.addEventListener('drop', e => {
            e.preventDefault();
            dropzone.classList.remove('bg-gray-100');
            if(checkFile(e.dataTransfer.files[0])){
                input.files = e.dataTransfer.files;
            }
        });
        input.addEventListener('change', () => {
            if(input.files.length && !checkFile(input.files[0])){
                input.value = '';
            }
        });
        const form = dropzone.closest('form');
        if(form){
            form.addEventListener('submit', (e) => {
                if(input.files.length && !checkFile(input.files[0])){
                    e.preventDefault();
                }
            });
        }
    }
    document.addEventListener('DOMContentLoaded', init);
})();
