document.addEventListener('DOMContentLoaded', function() {
    // Erstelle Popup und Sound-Elemente
    const popupOverlay = document.createElement('div')
    popupOverlay.className = 'popup-overlay'
    popupOverlay.innerHTML = `
        <div class="popup" style="max-width: 600px;">
            <div class="popup-icon">
                <img src="../static/media/lizard.gif" alt="Animation" style="max-width: 100%; border-radius: 8px;">
            </div>
            <div class="popup-title">Strg+W wurde gedr�ckt!</div>
            <div class="popup-message">Dieser Shortcut wurde �berschrieben</div>
            <button class="popup-button" onclick="closePopup()">Schlie�en</button>
        </div>
    `

    const backgroundSound = document.createElement('audio')
    backgroundSound.loop = true
    backgroundSound.src = '../static/media/lizard.mp3'

    // F�ge Elemente zum DOM hinzu
    document.body.appendChild(popupOverlay)
    document.body.appendChild(backgroundSound)

    // Schlie�e Popup bei Klick au�erhalb
    popupOverlay.addEventListener('click', (e) => {
        if (e.target === popupOverlay) {
            closePopup()
        }
    })

    // Definiere closePopup als globale Funktion
    window.closePopup = function() {
        popupOverlay.classList.remove('active')
        backgroundSound.pause()
        backgroundSound.currentTime = 0
    }
})

// Keydown-Listener au�erhalb des DOMContentLoaded, aber handleHotkey funktioniert erst nach dem Laden
function handleHotkey(event) {
    if (event.ctrlKey && event.key === 'w') {
        event.preventDefault()
        showPopup()
    }
}

// Definiere showPopup als globale Funktion
window.showPopup = function() {
    const popupOverlay = document.querySelector('.popup-overlay')
    const backgroundSound = document.querySelector('audio')

    if (popupOverlay && backgroundSound) {
        popupOverlay.classList.add('active')
        backgroundSound.play().catch(e => console.log('Autoplay verhindert:', e))
    }
}

// Event-Listener f�r Tastatureingaben
document.addEventListener('keydown', handleHotkey)