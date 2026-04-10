function validerRevenus() {
    const el = document.getElementById('rev-count');
    if (!el) return true;
    if (parseInt(el.value) < 12) {
        alert("⚠️ SAISIE INCOMPLÈTE\n\nVous n'avez saisi que " + el.value + " mois de revenus.\nIl faut impérativement 12 mois pour valider.");
        return false;
    }
    return true;
}

function validerActivites() {
    const el = document.getElementById('act-count');
    if (!el) return true;
    if (parseInt(el.value) < 12) {
        alert("⚠️ ACTIVITÉS INCOMPLÈTES\n\nVous avez saisi des rotations sur " + el.value + " mois seulement.\nVeuillez compléter l'année (même avec 0 activité si nécessaire) ou vérifier votre saisie.");
        return false;
    }
    return true;
}

function toggleCarFields() {
    var mode = document.getElementById('transport_mode').value;
    var rowVehicule = document.getElementById('row-vehicule');
    if (rowVehicule) {
        if (mode === 'Voiture') {
            rowVehicule.style.display = 'flex';
        } else {
            rowVehicule.style.display = 'none';
        }
    }
}

function updateBilan() {
    const getVal = (id) => { const el = document.getElementById(id); return el ? (parseFloat(el.value) || 0) : 0; };
    
    let totalFraisDiv = getVal('cotis') + getVal('uniforme') + getVal('bureau') + getVal('autre');
    let fraisKm = getVal('total-km-input') * 0.5; 
    let grandTotal = getVal('base-indem') + fraisKm + totalFraisDiv;
    
    const dDivers = document.getElementById('display-divers');
    if(dDivers) dDivers.innerText = totalFraisDiv.toLocaleString('fr-FR') + ' €';
    
    const dKm = document.getElementById('display-km-val');
    if(dKm) dKm.innerText = fraisKm.toLocaleString('fr-FR') + ' €';
    
    const dTotal = document.getElementById('display-total');
    if(dTotal) dTotal.innerText = grandTotal.toLocaleString('fr-FR') + ' €';
}

function updateFormMode() {
    const select = document.getElementById('mode_act');
    if (!select) return;
    const mode = select.value;
    const blockLC = document.getElementById('block-lc');
    const blockMC = document.getElementById('block-mc');
    if (!blockLC || !blockMC) return;
    
    if (mode === 'MC') { 
        blockLC.style.display = 'none'; blockMC.style.display = 'block'; updateMCInputs(); 
    } else { 
        blockLC.style.display = 'block'; blockMC.style.display = 'none'; 
    }
}

function updateMCInputs() {
    const elDep = document.getElementById('jour_dep');
    const elArr = document.getElementById('jour_arr');
    if (!elDep || !elArr) return;
    
    if (elDep.value && elArr.value) {
        const jDep = parseInt(elDep.value);
        const jArr = parseInt(elArr.value);
        let nb = 1;
        if (jArr >= jDep) { nb = jArr - jDep + 1; }
        const g1 = document.getElementById('group_escale_1');
        const g2 = document.getElementById('group_escale_2');
        const g3 = document.getElementById('group_escale_3');
        if(g1) g1.style.display = (nb >= 2) ? 'block' : 'none';
        if(g2) g2.style.display = (nb >= 3) ? 'block' : 'none';
        if(g3) g3.style.display = (nb >= 4) ? 'block' : 'none';
    }
}

function openHelp() { const el = document.getElementById("helpModal"); if(el) el.style.display = "block"; }
function closeHelp() { const el = document.getElementById("helpModal"); if(el) el.style.display = "none"; }
function openGuide() { const el = document.getElementById("guideModal"); if(el) el.style.display = "block"; }
function closeGuide() { const el = document.getElementById("guideModal"); if(el) el.style.display = "none"; }
function openUpload() { const el = document.getElementById("uploadModal"); if(el) el.style.display = "block"; }
function closeUpload() { const el = document.getElementById("uploadModal"); if(el) el.style.display = "none"; }
function openUploadEp4() { const el = document.getElementById("uploadModalEp4"); if(el) el.style.display = "block"; }
function closeUploadEp4() { const el = document.getElementById("uploadModalEp4"); if(el) el.style.display = "none"; }

// Moteur d'animation de la barre de progression
function animerProgression(barId, percentId, textId) {
    let bar = document.getElementById(barId);
    let percentText = document.getElementById(percentId);
    let textInfo = document.getElementById(textId);
    let width = 0;
    
    // Sécurité : si l'HTML n'a pas été bien collé, on arrête tout pour ne pas planter la page
    if (!bar || !percentText || !textInfo) return; 
    
    // Fait monter la barre rapidement au début, puis ralentit vers 90%
    let interval = setInterval(function() {
        if (width >= 90) {
            clearInterval(interval);
            textInfo.innerText = "⏳ Finalisation des calculs côté serveur...";
        } else {
            // Incrémentation aléatoire pour faire "vrai"
            let increment = Math.random() * (90 - width) * 0.15 + 1;
            width += increment;
            if(width > 90) width = 90;
            bar.style.width = width + '%';
            percentText.innerText = Math.round(width) + '%';
        }
    }, 400); // Mise à jour toutes les 400ms
}

function startUploadProcess() {
    const drop = document.getElementById('drop-zone');
    const loader = document.getElementById('loader-zone');
    const form = document.getElementById('form-upload');
    if (drop) drop.style.display = 'none';
    if (loader) loader.style.display = 'block';
    
    animerProgression('progress-bar-rev', 'progress-percent-rev', 'loading-text-rev');
    if (form) form.submit();
}

function startUploadProcessEp4() {
    const drop = document.getElementById('drop-zone-ep4');
    const loader = document.getElementById('loader-zone-ep4');
    const form = document.getElementById('form-upload-ep4');
    if (drop) drop.style.display = 'none';
    if (loader) loader.style.display = 'block';
    
    animerProgression('progress-bar-ep4', 'progress-percent-ep4', 'loading-text-ep4');
    if (form) form.submit();
}

window.onclick = function(event) { 
    if (event.target == document.getElementById("helpModal")) closeHelp(); 
    if (event.target == document.getElementById("guideModal")) closeGuide();
    if (event.target == document.getElementById("uploadModal")) closeUpload();
    if (event.target == document.getElementById("uploadModalEp4")) closeUploadEp4();
}

window.onload = function() {
    var hasError = document.getElementById('flag-upload-error');
    if (hasError) openUpload();
    
    toggleCarFields();
    updateFormMode();
};
function updateBilan() {
            const getVal = (id) => { const el = document.getElementById(id); return el ? (parseFloat(el.value) || 0) : 0; };
            
            let totalFraisDiv = getVal('cotis') + getVal('uniforme') + getVal('bureau') + getVal('autre');
            let fraisKm = getVal('total-km-input') * 0.5; 
            let baseIndem = getVal('base-indem');
            let grandTotal = baseIndem + fraisKm + totalFraisDiv;
            
            // Mise à jour des textes
            const dDivers = document.getElementById('display-divers');
            if(dDivers) dDivers.innerText = totalFraisDiv.toLocaleString('fr-FR') + ' €';
            
            const dKm = document.getElementById('display-km-val');
            if(dKm) dKm.innerText = fraisKm.toLocaleString('fr-FR') + ' €';
            
            const dTotal = document.getElementById('display-total');
            if(dTotal) dTotal.innerText = grandTotal.toLocaleString('fr-FR') + ' €';

            // Alerte intelligente si 'Autre' dépasse 500€
            const alertAutre = document.getElementById('warning-autre');
            if(alertAutre) {
                alertAutre.style.display = getVal('autre') > 500 ? 'block' : 'none';
            }

            // Mise à jour visuelle du graphique en temps réel
            if (typeof myChart !== 'undefined') {
                myChart.data.datasets[0].data = [baseIndem, fraisKm, totalFraisDiv];
                myChart.update();
            }
        }