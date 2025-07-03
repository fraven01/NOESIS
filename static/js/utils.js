function showSpinner(buttonElement, spinnerText = 'Wird geladen...') {
    if (!buttonElement) return;
    buttonElement.dataset.originalHtml = buttonElement.innerHTML;
    buttonElement.disabled = true;
    buttonElement.innerHTML = `<span class="spinner"></span>${spinnerText ? ' ' + spinnerText : ''}`;
}

function hideSpinner(buttonElement) {
    if (!buttonElement) return;
    const original = buttonElement.dataset.originalHtml;
    if (original !== undefined) {
        buttonElement.innerHTML = original;
    }
    buttonElement.disabled = false;
}

function getCookie(name) {
    const match = document.cookie.match('(^|;)\\s*' + name + '=([^;]*)');
    return match ? decodeURIComponent(match[2]) : null;
}

document.body.addEventListener('htmx:configRequest', (evt) => {
    const token = getCookie('csrftoken');
    if (token) evt.detail.headers['X-CSRFToken'] = token;
});
