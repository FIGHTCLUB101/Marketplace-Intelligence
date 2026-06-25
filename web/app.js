import AppState from './state.js';

document.addEventListener('DOMContentLoaded', () => {
  const data = window.GOAT_DATA;
  if (!data){ console.error('GOAT_DATA missing'); return; }

  document.getElementById('stat-localities').textContent = data.summary.total_localities;
  document.getElementById('stat-go').textContent = data.summary.go;
  document.getElementById('stat-qc').textContent = data.summary.qc_ready;
  document.getElementById('stat-gyms').textContent = data.summary.total_gyms.toLocaleString();
  document.getElementById('stat-ds').textContent = data.summary.total_darkstores.toLocaleString();

  if (AppState.initMargin) AppState.initMargin();
  if (AppState.renderMethodology) AppState.renderMethodology(data);
  if (AppState.renderLeaderboard) AppState.renderLeaderboard(data);

  Promise.all([
    fetch('data-markers.json').then(r=>r.json()),
    fetch('darkstores.json').then(r=>r.json()),
  ]).then(([markers, ds]) => {
    AppState.markers = markers;
    const darkstores = (ds.markers || []).map(m => ({lat:m.lat,lng:m.lng,brand:m.brand}));
    if (AppState.initMap) AppState.initMap(data, markers, darkstores);
    if (AppState.renderGyms) AppState.renderGyms(data, markers);
    if (AppState.renderWhitespace) AppState.renderWhitespace(data);
  }).catch(e=>console.error('data load failed', e));

  const tabs = document.querySelectorAll('.nav-tab');
  const views = document.querySelectorAll('.page-view');
  tabs.forEach(tab => tab.addEventListener('click', () => {
    const id = tab.dataset.target;
    tabs.forEach(t=>t.classList.remove('active'));
    views.forEach(v=>v.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(id).classList.add('active');
    if (id === 'map-view' && AppState.mapInstance) setTimeout(()=>AppState.mapInstance.resize(),100);
  }));
});
