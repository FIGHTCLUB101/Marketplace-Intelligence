import { test } from 'node:test';
import assert from 'node:assert';
import { verdictColor, inspectorHTML } from '../scoreDisplay.js';

test('verdictColor maps each verdict', () => {
  assert.equal(verdictColor('GO'), '#059669');
  assert.equal(verdictColor('SAMPLE-FIRST'), '#d97706');
  assert.equal(verdictColor('WAIT'), '#52525b');
});

test('inspectorHTML includes area, score, verdict, channel', () => {
  const html = inspectorHTML({ area:'Sohna Road', city:'Gurugram', goat_fit:82.5,
    verdict:'GO', channel:'Blinkit + B2B', affluence:90, fitness:80, corporate:70, youth:40,
    partial_data:false });
  assert.ok(html.includes('Sohna Road'));
  assert.ok(html.includes('82.5'));
  assert.ok(html.includes('GO'));
  assert.ok(html.includes('Blinkit + B2B'));
});

test('inspectorHTML shows serviceability, archetype, activation, source', () => {
  const html = inspectorHTML({ area:'Sohna Road', city:'Gurugram', goat_fit:82, verdict:'GO',
    channel:'Blinkit + B2B', affluence:90, fitness:80, corporate:70, youth:40, partial_data:false,
    qc_serviceable:true, nearest_by_brand:{Blinkit:1.2}, archetype:'Corporate Belt',
    activation:[{type:'mall',name:'Sapphire Mall'}], health_ecosystem:true,
    nearby_raw:'Sector 47, Sector 48', url:'https://magicbricks.com/x' });
  assert.ok(html.includes('QC-ready'));
  assert.ok(html.includes('Corporate Belt'));
  assert.ok(html.includes('Sapphire Mall'));
  assert.ok(html.includes('magicbricks.com'));
});
