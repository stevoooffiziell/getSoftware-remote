document.getElementById('loginForm').addEventListener('submit', function(event) {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('errorMessage');

    // Einfache Validierung - in einer echten Anwendung würden Sie
    // die Anmeldedaten an den Server senden
    if (username.trim() === '' || password.trim() === '') {
        event.preventDefault();
        errorMessage.style.display = 'block';
    }
});

// Prüfen, ob eine Flash-Nachricht für ungültige Anmeldedaten vorhanden ist
document.addEventListener('DOMContentLoaded', function() {
    // Diese Prüfung simuliert das Vorhandensein einer Flash-Nachricht
    // In der echten Anwendung würden Sie das serverseitig setzen
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('error') === 'auth') {
        showPopup();
    }
});

function showPopup() {
    document.getElementById('errorPopup').classList.add('active');
}