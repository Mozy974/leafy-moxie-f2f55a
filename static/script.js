// State
let activeShift = null;
let timerInterval = null;

// DOM Elements
const timeDisplay = document.getElementById('current-time');
const dateDisplay = document.getElementById('current-date');
const statusDisplay = document.getElementById('clock-status');
const elapsedTimeDisplay = document.getElementById('elapsed-time');

const btnClockIn = document.getElementById('btn-clock-in');
const btnClockOut = document.getElementById('btn-clock-out');

const shiftsList = document.getElementById('shifts-list');
const incidentsList = document.getElementById('incidents-list');

const tabs = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');

const incidentForm = document.getElementById('incident-form');
const fileInput = document.getElementById('incident-image');
const fileNameDisplay = document.getElementById('file-name');

// Utils
function getImageUrl(path) {
    if (!path) return '';
    if (path.startsWith('http')) return path;
    return path.startsWith('/') ? path : `/uploads/${path}`;
}

// 1. Clock and UI Updates
function updateLiveClock() {
    const now = new Date();
    timeDisplay.textContent = now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateDisplay.textContent = now.toLocaleDateString('fr-FR', options).toUpperCase();
}
setInterval(updateLiveClock, 1000);
updateLiveClock();

function updateElapsedTime() {
    if (!activeShift) return;
    const now = new Date();
    const start = new Date(activeShift.clock_in + "Z"); // Make sure parse as UTC
    const diff = Math.floor((now - start) / 1000); // seconds
    
    if (diff < 0) return; // Timezone safety

    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;
    
    elapsedTimeDisplay.textContent = `${hours}h ${minutes}m ${seconds}s`;
}

// 2. Tab Navigation
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        // Remove active class
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        // Add active class
        tab.classList.add('active');
        document.getElementById(tab.dataset.target).classList.add('active');
    });
});

// 3. API Calls (Shifts)
async function fetchShifts() {
    try {
        const res = await fetch('/api/shifts');
        const data = await res.json();
        
        // Detect if top shift is active
        if (data.shifts && data.shifts.length > 0) {
            const lastShift = data.shifts[0];
            if (!lastShift.clock_out) {
                activeShift = lastShift;
                showClockOutUI();
            } else {
                activeShift = null;
                showClockInUI();
            }
        } else {
            activeShift = null;
            showClockInUI();
        }
        
        renderShifts(data.shifts);
        updateWeeklySummary(data.shifts);
    } catch (e) {
        console.error('Error fetching shifts', e);
    }
}

function updateWeeklySummary(shifts) {
    const totalHoursElement = document.getElementById('total-hours-week');
    const totalShiftsElement = document.getElementById('total-shifts-week');
    
    if (!shifts || shifts.length === 0) {
        totalHoursElement.textContent = '0h 00m';
        totalShiftsElement.textContent = '0';
        return;
    }

    const now = new Date();
    // Get Monday of current week
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1); // adjust when day is sunday
    const monday = new Date(now.setDate(diff));
    monday.setHours(0, 0, 0, 0);

    let totalMinutes = 0;
    let count = 0;

    shifts.forEach(shift => {
        const shiftDate = new Date(shift.clock_in + "Z");
        if (shiftDate >= monday) {
            count++;
            if (shift.duration_minutes) {
                totalMinutes += shift.duration_minutes;
            }
        }
    });

    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    
    totalHoursElement.textContent = `${hours}h ${minutes.toString().padStart(2, '0')}m`;
    totalShiftsElement.textContent = count;
}

function showClockInUI() {
    btnClockIn.style.display = 'flex';
    btnClockOut.style.display = 'none';
    statusDisplay.textContent = 'HORS SERVICE';
    statusDisplay.classList.remove('active');
    elapsedTimeDisplay.style.display = 'none';
    clearInterval(timerInterval);
}

function showClockOutUI() {
    btnClockIn.style.display = 'none';
    btnClockOut.style.display = 'flex';
    statusDisplay.textContent = 'EN SERVICE';
    statusDisplay.classList.add('active');
    elapsedTimeDisplay.style.display = 'block';
    
    updateElapsedTime();
    timerInterval = setInterval(updateElapsedTime, 1000);
}

btnClockIn.addEventListener('click', async () => {
    btnClockIn.disabled = true;
    try {
        const res = await fetch('/api/clock_in', { method: 'POST' });
        const data = await res.json();
        if(data.success) {
            activeShift = data.shift;
            showClockOutUI();
            showToast('Service commencé !');
            fetchShifts();
        }
    } catch (e) {
        alert('Erreur réseau');
    }
    btnClockIn.disabled = false;
});

btnClockOut.addEventListener('click', async () => {
    btnClockOut.disabled = true;
    try {
        const res = await fetch('/api/clock_out', { method: 'POST' });
        const data = await res.json();
        if(data.success) {
            activeShift = null;
            showClockInUI();
            showToast('Service terminé !');
            fetchShifts();
        }
    } catch (e) {
        alert('Erreur réseau');
    }
    btnClockOut.disabled = false;
});

function renderShifts(shifts) {
    shiftsList.innerHTML = '';
    
    // Group by date... for simplicity just list them
    shifts.forEach(shift => {
        const li = document.createElement('li');
        li.className = 'shift-item';
        
        const inDate = new Date(shift.clock_in + "Z");
        const inStr = inDate.toLocaleTimeString('fr-FR', {hour: '2-digit', minute:'2-digit'});
        const dateStr = inDate.toLocaleDateString('fr-FR', {day: '2-digit', month: 'short'});
        
        let outStr = '...';
        let durStr = '--';
        
        if (shift.clock_out) {
            const outDate = new Date(shift.clock_out + "Z");
            outStr = outDate.toLocaleTimeString('fr-FR', {hour: '2-digit', minute:'2-digit'});
            
            const rh = Math.floor(shift.duration_minutes / 60);
            const rm = shift.duration_minutes % 60;
            durStr = rh > 0 ? `${rh}h ${rm}m` : `${rm} min`;
        }

        li.innerHTML = `
            <div class="shift-dates">
                <strong>${dateStr}</strong>
                <span>${inStr} - ${outStr}</span>
            </div>
            <div class="shift-duration">
                ${durStr}
            </div>
        `;
        shiftsList.appendChild(li);
    });
}

// 4. API Calls (Incidents)
fileInput.addEventListener('change', (e) => {
    if(e.target.files.length > 0) {
        fileNameDisplay.textContent = e.target.files[0].name;
    } else {
        fileNameDisplay.textContent = 'Aucune photo...';
    }
});

incidentForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-incident');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Envoi...';
    btn.disabled = true;

    const formData = new FormData(incidentForm);
    try {
        const res = await fetch('/api/incident', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if(data.success) {
            showToast('Incident signalé !');
            incidentForm.reset();
            fileNameDisplay.textContent = 'Aucune photo...';
            fetchIncidents();
            // Optional: return to first tab
            tabs[0].click();
        }
    } catch(err) {
        alert("Erreur lors de l'envoi");
    }
    
    btn.innerHTML = 'Envoyer le rapport';
    btn.disabled = false;
});

async function fetchIncidents() {
    try {
        const res = await fetch('/api/incidents');
        const data = await res.json();
        renderIncidents(data.incidents);
    } catch (e) {
        console.error(e);
    }
}

function renderIncidents(incidents) {
    incidentsList.innerHTML = '';
    incidents.forEach(inc => {
        const li = document.createElement('li');
        li.className = 'incident-item';
        
        const dateStr = new Date(inc.timestamp + "Z").toLocaleDateString('fr-FR', {day: 'numeric', month: 'short', hour:'2-digit', minute:'2-digit'});
        
        let imgHtml = '';
        if (inc.image_path) {
            imgHtml = `<img src="${getImageUrl(inc.image_path)}" class="incident-img" alt="Photo" onclick="window.open(this.src)">`;
        }
        
        li.innerHTML = `
            <div class="incident-header">
                <span class="incident-badge">${inc.type}</span>
                <span class="incident-date">${dateStr}</span>
            </div>
            ${inc.description ? `<p class="incident-desc">${inc.description}</p>` : ''}
            ${imgHtml}
        `;
        incidentsList.appendChild(li);
    });
}

// Utils
function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => {
         toast.classList.remove('show');
    }, 3000);
}

// Init
fetchShifts();
fetchIncidents();
fetchInterventions();

// 5. API Calls (Interventions Avant/Après)
const interventionStartForm = document.getElementById('intervention-start-form');
const interventionEndForm = document.getElementById('intervention-end-form');
const startInterventionCard = document.getElementById('start-intervention-card');
const activeInterventionCard = document.getElementById('active-intervention-card');
const interventionsList = document.getElementById('interventions-list');
const fileInputBefore = document.getElementById('intervention-before');
const fileNameBefore = document.getElementById('file-name-before');
const fileInputAfter = document.getElementById('intervention-after');
const fileNameAfter = document.getElementById('file-name-after');
const btnCancelIntervention = document.getElementById('btn-cancel-intervention');

let activeIntervention = null;

fileInputBefore.addEventListener('change', (e) => {
    if(e.target.files.length > 0) fileNameBefore.textContent = e.target.files[0].name;
    else fileNameBefore.textContent = 'Aucune photo...';
});
fileInputAfter.addEventListener('change', (e) => {
    if(e.target.files.length > 0) fileNameAfter.textContent = e.target.files[0].name;
    else fileNameAfter.textContent = 'Aucune photo...';
});

async function fetchInterventions() {
    try {
        const res = await fetch('/api/interventions');
        const data = await res.json();
        const pending = data.interventions.find(i => !i.timestamp_end);
        
        if (pending) {
            activeIntervention = pending;
            startInterventionCard.style.display = 'none';
            activeInterventionCard.style.display = 'block';
            document.getElementById('active-intervention-loc').textContent = pending.location;
            document.getElementById('active-intervention-id').value = pending.id;
            
            // Show preview if image exists
            if (pending.image_before_path) {
                document.getElementById('active-intervention-img').src = getImageUrl(pending.image_before_path);
            }
        } else {
            activeIntervention = null;
            startInterventionCard.style.display = 'block';
            activeInterventionCard.style.display = 'none';
        }
        
        renderInterventions(data.interventions.filter(i => i.timestamp_end));
    } catch(e) { console.error(e); }
}

interventionStartForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-intervention-start');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>...';
    btn.disabled = true;

    const formData = new FormData(interventionStartForm);
    try {
        const res = await fetch('/api/intervention/start', { method: 'POST', body: formData });
        const data = await res.json();
        if(data.success) {
            showToast('Intervention commencée !');
            interventionStartForm.reset();
            fileNameBefore.textContent = 'Aucune photo...';
            fetchInterventions();
        }
    } catch(err) { alert("Erreur d'envoi"); }
    btn.innerHTML = 'Démarrer (Avant)';
    btn.disabled = false;
});

interventionEndForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-intervention-end');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>...';
    btn.disabled = true;

    const intId = document.getElementById('active-intervention-id').value;
    const formData = new FormData(interventionEndForm);
    try {
        const res = await fetch(`/api/intervention/end/${intId}`, { method: 'POST', body: formData });
        const data = await res.json();
        if(data.success) {
            showToast('Intervention terminée !');
            interventionEndForm.reset();
            fileNameAfter.textContent = 'Aucune photo...';
            fetchInterventions();
        }
    } catch(err) { alert("Erreur d'envoi"); }
    btn.innerHTML = 'Terminer (Après)';
    btn.disabled = false;
});

btnCancelIntervention.addEventListener('click', () => {
    // Basic cancel logic - we don't have a route for deleting, but we can hide it 
    // Usually we would call a delete API. Here we just pretend or let them reset the form
    if(confirm('Annuler l\'intervention en cours ?')) {
        // Ideally fetch DELETE. Since no delete route, we will just reset UI
        startInterventionCard.style.display = 'block';
        activeInterventionCard.style.display = 'none';
        activeIntervention = null;
    }
});

function renderInterventions(interventions) {
    interventionsList.innerHTML = '';
    interventions.forEach(inc => {
        const li = document.createElement('li');
        li.className = 'incident-item';
        
        const dateStr = new Date(inc.timestamp_start + "Z").toLocaleDateString('fr-FR', {day: 'numeric', month: 'short', hour:'2-digit', minute:'2-digit'});
        
        li.innerHTML = `
            <div class="incident-header">
                <span class="incident-badge" style="background:var(--accent-blue)">${inc.location}</span>
                <span class="incident-date">${dateStr}</span>
            </div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <div style="flex:1">
                    <span style="font-size:11px; color:#8b949e">AVANT</span>
                    <img src="${getImageUrl(inc.image_before_path)}" alt="Avant" style="width:100%; border-radius:8px; max-height:100px; object-fit:cover;">
                </div>
                <div style="flex:1">
                    <span style="font-size:11px; color:#8b949e">APRÈS</span>
                    <img src="${getImageUrl(inc.image_after_path)}" alt="Après" style="width:100%; border-radius:8px; max-height:100px; object-fit:cover;">
                </div>
            </div>
        `;
        interventionsList.appendChild(li);
    });
}

// 6. Service Worker Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
            .then(reg => console.log('Service Worker enregistré !'))
            .catch(err => console.error('Erreur SW:', err));
    });
}

// 7. Network Status Feedback
window.addEventListener('online', () => {
    showToast('Connexion rétablie !');
    document.body.classList.remove('is-offline');
});
window.addEventListener('offline', () => {
    showToast('Vous êtes hors connexion. L\'interface reste accessible, mais les envois échoueront.');
    document.body.classList.add('is-offline');
});
if (!navigator.onLine) document.body.classList.add('is-offline');
