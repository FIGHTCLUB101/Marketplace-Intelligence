import { test } from 'node:test';
import assert from 'node:assert';
import { colorFor, labelFor } from '../contract.js';
import { buildFilter } from '../filters.js';

test('contract colors + labels', () => {
  assert.equal(colorFor('PUSH-NOW'), '#059669');
  assert.equal(colorFor('???'), '#888780');
  assert.equal(labelFor('PUSH-NOW'), 'Push now');
});
test('buildFilter all-pass is null', () => {
  assert.equal(buildFilter({ city: 'all', verdict: 'all', serviceability: 'all', gtm: null }), null);
});
test('buildFilter composes facets', () => {
  const f = buildFilter({ city: 'Mumbai', verdict: 'GO', serviceability: 'all', gtm: null });
  assert.equal(f[0], 'all');
  assert.deepEqual(f[1], ['==', ['get', 'ADDRESS'], 'Mumbai']);
  assert.deepEqual(f[2], ['==', ['get', 'icp_verdict'], 'GO']);
});
test('buildFilter gtm set -> in expr', () => {
  const f = buildFilter({ city: 'all', verdict: 'all', serviceability: 'all', gtm: new Set(['PUSH-NOW']) });
  assert.deepEqual(f[1], ['in', ['get', 'gtm_action'], ['literal', ['PUSH-NOW']]]);
});
