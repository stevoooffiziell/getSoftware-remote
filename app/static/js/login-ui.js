document.getElementById('loginForm').addEventListener('submit', function(event) {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('errorMessage');

    // Einfache Validierung - in einer echten Anwendung w�rden Sie
    // die Anmeldedaten an den Server senden
    if (username.trim() === '' || password.trim() === '') {
        event.preventDefault();
        errorMessage.style.display = 'block';
    }
});

// Pr�fen, ob eine Flash-Nachricht f�r ung�ltige Anmeldedaten vorhanden ist
document.addEventListener('DOMContentLoaded', function() {
    // Diese Pr�fung simuliert das Vorhandensein einer Flash-Nachricht
    // In der echten Anwendung w�rden Sie das serverseitig setzen
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('error') === 'auth') {
        showPopup();
    }
});

function showPopup() {
    document.getElementById('errorPopup').classList.add('active');
}