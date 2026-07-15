import { test } from 'node:test';
import assert from 'node:assert';
import {
  computeVisibilityRate, formatBrandDefenceRate, formatTrendRows, groupChangesByProduct,
  normalizeBrandName, severityFor,
} from '../shelf-monitor.js';

test('severityFor: critical when goat_displaced or goat_gone non-empty', () => {
  assert.equal(severityFor({ goat_displaced: [{}], goat_gone: [], rank_intrusions: [] }), 'critical');
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [{}], rank_intrusions: [] }), 'critical');
});

test('severityFor: warning when only rank_intrusions non-empty', () => {
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [], rank_intrusions: [{}] }), 'warning');
});

test('severityFor: clear when everything empty', () => {
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [], rank_intrusions: [] }), 'clear');
});

test('formatTrendRows maps weeks to cells, using — for missing data points', () => {
  const trends = {
    weeks: ['2026-07-06', '2026-07-13'],
    series: [
      { product_name: 'GOAT Life Mocha Marvel', is_goat: true, data: [1.0, null] },
      { product_name: 'Prustlr Discovery Protein Oats', is_goat: false, data: [null, 5.0] },
    ],
  };
  const rows = formatTrendRows(trends);
  assert.deepEqual(rows[0], { label: 'GOAT Life Mocha Marvel', isGoat: true, cells: [1.0, '—'] });
  assert.deepEqual(rows[1], { label: 'Prustlr Discovery Protein Oats', isGoat: false, cells: ['—', 5.0] });
});

test('formatBrandDefenceRate: formats a number, handles null', () => {
  assert.equal(formatBrandDefenceRate(75.0), '75.0%');
  assert.equal(formatBrandDefenceRate(0), '0.0%');
  assert.equal(formatBrandDefenceRate(null), 'N/A');
});

test('normalizeBrandName strips a trailing " Oats" suffix', () => {
  assert.equal(normalizeBrandName('Pintola Oats'), 'Pintola');
  assert.equal(normalizeBrandName('The Whole Truth Oats'), 'The Whole Truth');
  assert.equal(normalizeBrandName('Pintola'), 'Pintola');
});

test('computeVisibilityRate: percentage of is_goat rows, null for empty', () => {
  assert.equal(computeVisibilityRate([]), null);
  assert.equal(computeVisibilityRate([{ is_goat: true }, { is_goat: false }]), 50);
  assert.equal(computeVisibilityRate([{ is_goat: false }, { is_goat: false }]), 0);
  assert.equal(computeVisibilityRate([{ is_goat: true }]), 100);
});

test('groupChangesByProduct groups same (eventType, product) pairs and counts entries', () => {
  const changes = {
    goat_displaced: [
      { city: 'Mumbai', locality: 'Sion', rank: 1, was: 'GOAT Life Mocha Marvel', now: 'MISSING' },
      { city: 'Pune', locality: 'Wakad', rank: 2, was: 'GOAT Life Mocha Marvel', now: 'Still listed, now rank 5' },
    ],
    goat_gone: [],
    rank_intrusions: [
      { city: 'Delhi', locality: 'Saket', rank: 1, intruder: 'Yoga Bar Oats' },
    ],
    price_changes: [],
    new_products: [],
    gone_products: [
      { city: 'Pune', locality: 'Baner', rank: 4, product: 'Saffola Oats', is_goat: false },
      { city: 'Delhi', locality: 'Saket', rank: 2, product: 'GOAT Life Mocha Marvel', is_goat: true },
    ],
  };
  const groups = groupChangesByProduct(changes);
  assert.equal(groups.length, 3);

  const displaced = groups.find((g) => g.eventType === 'goat_displaced');
  assert.equal(displaced.product, 'GOAT Life Mocha Marvel');
  assert.equal(displaced.severity, 'critical');
  assert.equal(displaced.entries.length, 2);
  assert.deepEqual(displaced.entries[0], { city: 'Mumbai', locality: 'Sion', detail: 'MISSING' });

  const intrusion = groups.find((g) => g.eventType === 'rank_intrusions');
  assert.equal(intrusion.severity, 'warning');
  assert.equal(intrusion.entries[0].detail, 'intruded at rank 1');

  // GOAT's own gone_products entry (is_goat: true) must be excluded.
  const gone = groups.find((g) => g.eventType === 'gone_products');
  assert.equal(gone.entries.length, 1);
  assert.equal(gone.product, 'Saffola Oats');
});

test('groupChangesByProduct formats detail strings for goat_gone, price_changes, and new_products', () => {
  const changes = {
    goat_displaced: [],
    goat_gone: [
      { city: 'Chennai', locality: 'Adyar', rank: 3, product: 'GOAT Life Mocha Marvel', is_goat: true },
    ],
    rank_intrusions: [],
    price_changes: [
      { city: 'Bangalore', locality: 'Koramangala', product: 'Yoga Bar Oats', old_price: 98, new_price: 230, change: 132 },
      { city: 'Bangalore', locality: 'HSR Layout', product: 'Yoga Bar Oats', old_price: 230, new_price: 98, change: -132 },
    ],
    new_products: [
      { city: 'Pune', locality: 'Baner', rank: 7, product: 'Tata Soulfull Berry Chia Protein Oats' },
    ],
    gone_products: [],
  };
  const groups = groupChangesByProduct(changes);

  const gone = groups.find((g) => g.eventType === 'goat_gone');
  assert.equal(gone.severity, 'critical');
  assert.equal(gone.entries[0].detail, 'last seen rank 3');

  const priceChanges = groups.find((g) => g.eventType === 'price_changes');
  assert.equal(priceChanges.severity, 'warning');
  assert.equal(priceChanges.entries[0].detail, '▲₹132 (₹98 → ₹230)');
  assert.equal(priceChanges.entries[1].detail, '▼₹132 (₹230 → ₹98)');

  const appeared = groups.find((g) => g.eventType === 'new_products');
  assert.equal(appeared.severity, 'info');
  assert.equal(appeared.entries[0].detail, 'appeared at rank 7');
});

test('groupChangesByProduct returns an empty array for no changes', () => {
  const changes = {
    goat_displaced: [], goat_gone: [], rank_intrusions: [], price_changes: [],
    new_products: [], gone_products: [],
  };
  assert.deepEqual(groupChangesByProduct(changes), []);
});
