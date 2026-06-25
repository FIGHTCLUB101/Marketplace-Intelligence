import AppState from './state.js';
import { inspectorHTML } from './scoreDisplay.js';

function geojson(points, propsFn){
  return { type:'FeatureCollection', features: points
    .filter(p => p.lat != null && p.lng != null)
    .map(p => ({ type:'Feature', geometry:{type:'Point',coordinates:[p.lng,p.lat]}, properties: propsFn(p) })) };
}

const DS_COLOR = { 'Blinkit':'#f59e0b', 'Zepto':'#a855f7', 'Swiggy Instamart':'#f97316' };

function initMap(data, markers, darkstores){
  const map = new maplibregl.Map({
    container:'map-container', style:'https://tiles.openfreemap.org/styles/dark',
    center:[78.9629,20.5937], zoom:4.5, minZoom:3, maxZoom:16,
  });
  AppState.mapInstance = map;
  map.addControl(new maplibregl.NavigationControl(), 'top-right');

  map.on('load', () => {
    // darkstores (3 brand layers, underneath)
    map.addSource('darkstores', { type:'geojson', data: geojson(darkstores, d => ({brand:d.brand})) });
    [['Blinkit','ds-blinkit'],['Zepto','ds-zepto'],['Swiggy Instamart','ds-instamart']].forEach(([brand,id])=>{
      map.addLayer({ id, type:'circle', source:'darkstores',
        filter:['==',['get','brand'],brand],
        paint:{ 'circle-radius':2, 'circle-color':DS_COLOR[brand], 'circle-opacity':.45 } });
    });

    map.addSource('stores', { type:'geojson', data: geojson(markers.stores, s => ({})) });
    map.addLayer({ id:'stores', type:'circle', source:'stores',
      paint:{ 'circle-radius':4, 'circle-color':'#3b82f6', 'circle-opacity':.6 } });

    map.addSource('gyms', { type:'geojson', data: geojson(markers.gyms, g => ({})) });
    map.addLayer({ id:'gyms', type:'circle', source:'gyms',
      paint:{ 'circle-radius':2.5, 'circle-color':'#a1a1aa', 'circle-opacity':.4 } });

    map.addSource('localities', { type:'geojson',
      data: geojson(data.localities, l => ({ idx:data.localities.indexOf(l), verdict:l.verdict, fit:l.goat_fit })) });
    map.addLayer({ id:'localities', type:'circle', source:'localities',
      paint:{
        'circle-radius':['interpolate',['linear'],['get','fit'],0,4,100,11],
        'circle-color':['match',['get','verdict'],'GO','#059669','SAMPLE-FIRST','#d97706','#52525b'],
        'circle-stroke-width':1, 'circle-stroke-color':'#09090b', 'circle-opacity':.85,
      } });

    map.on('click','localities',(e)=>AppState.showLocality(data.localities[e.features[0].properties.idx]));
    map.on('mouseenter','localities',()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave','localities',()=>map.getCanvas().style.cursor='');

    // toggle wiring
    const toggle = (id, layers) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => layers.forEach(L =>
        map.setLayoutProperty(L, 'visibility', el.checked ? 'visible' : 'none')));
    };
    toggle('tg-blinkit',['ds-blinkit']); toggle('tg-zepto',['ds-zepto']);
    toggle('tg-instamart',['ds-instamart']); toggle('tg-gyms',['gyms']); toggle('tg-stores',['stores']);
  });
}

function showLocality(loc){
  document.getElementById('inspector').innerHTML = inspectorHTML(loc);
  if (AppState.mapInstance && loc.lat != null){
    AppState.mapInstance.easeTo({ center:[loc.lng,loc.lat], zoom:11, duration:700 });
  }
}

AppState.initMap = initMap;
AppState.showLocality = showLocality;
