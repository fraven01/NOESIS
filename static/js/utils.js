function safeJsonParse(jsonString) {
    if (!jsonString || jsonString.trim() === "") {
        return {};
    }
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        console.error("Fehler beim Parsen von JSON:", jsonString, e);
        return {};
    }
}

window.SPINNER_HTML = '<span class="inline-block w-4 h-4 border-2 border-current border-r-transparent rounded-full animate-spin align-[-0.125em]"></span>';

function showSpinner(buttonElement, spinnerText = 'Wird geladen...') {
    if (!buttonElement) return;
    buttonElement.dataset.originalHtml = buttonElement.innerHTML;
    buttonElement.disabled = true;
    buttonElement.innerHTML = `${window.SPINNER_HTML}${spinnerText ? ' ' + spinnerText : ''}`;
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

document.body.addEventListener('refresh-cockpit', () => {
    if (window.htmx) {
        htmx.trigger('#projekt-cockpit', 'refresh-cockpit');
    }
});
