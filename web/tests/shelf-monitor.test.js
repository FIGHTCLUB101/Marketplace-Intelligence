import { test } from 'node:test';
import assert from 'node:assert';
import { formatBrandDefenceRate, formatTrendRows, severityFor } from '../shelf-monitor.js';

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
