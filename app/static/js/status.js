document.addEventListener('DOMContentLoaded', function() {
    console.log('status.js geladen ñ DOM ready');

    // 1. Service Toggle
    const serviceToggle = document.getElementById('serviceToggle');
    if (serviceToggle) {
        serviceToggle.addEventListener('change', function() {
            const action = this.checked ? 'start-service' : 'stop-service';
            fetch(action, { method: 'POST' })
                .then(response => {
                    if (response.ok) {
                        location.reload();  // Erfolgreich ? Reload
                    } else {
                        alert('Aktion fehlgeschlagen!');
                        this.checked = !this.checked;  // Toggle zur¸ck
                    }
                })
                .catch(error => {
                    console.error('Service Toggle Fehler:', error);
                    this.checked = !this.checked;
                });
        });
    }

    // 2. Reset Database Modal
    const resetBtn = document.getElementById('resetDbBtn');
    const modal = document.getElementById('confirmModal');
    const confirmCheckbox = document.getElementById('confirmCheckbox');
    const confirmBtn = document.getElementById('confirmBtn');
    const cancelBtn = document.getElementById('cancelBtn');

    if (resetBtn && modal) {
        resetBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Reset Button geklickt');
            modal.style.display = 'flex';  // Vollbild-Modal ˆffnen
        });
    }

    if (confirmCheckbox && confirmBtn) {
        confirmCheckbox.addEventListener('change', function() {
            confirmBtn.disabled = !this.checked;
        });
    }

    if (confirmBtn) {
        confirmBtn.addEventListener('click', function() {
            fetch('/reset-database', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('? Datenbank zur¸ckgesetzt!');
                        location.reload();
                    } else {
                        alert('? Fehler: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('DB Reset Fehler:', error);
                    alert('? Netzwerkfehler!');
                })
                .finally(() => {
                    closeModal();  // Immer schlieﬂen
                });
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeModal);
    }

    // ESC-Taste + Overlay-Klick schlieﬂen
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            closeModal();
        }
    });

    modal?.addEventListener('click', function(e) {
        if (e.target === modal) closeModal();
    });

    function closeModal() {
        modal.style.display = 'none';
        if (confirmCheckbox) confirmCheckbox.checked = false;
        if (confirmBtn) confirmBtn.disabled = true;
    }
});
