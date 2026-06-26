import { test } from 'node:test';
import assert from 'node:assert';
import { assignWave, buildSequence } from '../sequence.js';

test('assignWave first-match wins', () => {
  assert.equal(assignWave({ icp_verdict: 'GO', serviceability_state: 'Confirmed', lifecycle: 'established' }), 1);
  assert.equal(assignWave({ icp_verdict: 'GO', serviceability_state: 'Confirmed', lifecycle: 'emerging' }), 2);
  assert.equal(assignWave({ icp_verdict: 'GO', serviceability_state: 'Likely', lifecycle: 'x' }), 3);
  assert.equal(assignWave({ icp_verdict: 'SAMPLE-FIRST', serviceability_state: 'Confirmed', lifecycle: 'established' }), 4);
  assert.equal(assignWave({ icp_verdict: 'WAIT', serviceability_state: 'Unknown', lifecycle: 'x', hidden_gem_v2: true }), 5);
  assert.equal(assignWave({ icp_verdict: 'WAIT', serviceability_state: 'Unknown', lifecycle: 'x' }), 0);
});

test('buildSequence respects budget + platform', () => {
  const locs = [
    { ADDRESS: 'X', icp_verdict: 'GO', serviceability_state: 'Confirmed', lifecycle: 'established', icp_score: 90, archetype_ml: 'Premium', blinkit_confirmed: true },
    { ADDRESS: 'X', icp_verdict: 'GO', serviceability_state: 'Confirmed', lifecycle: 'established', icp_score: 80, archetype_ml: 'Premium', blinkit_confirmed: false },
    { ADDRESS: 'Y', icp_verdict: 'GO', serviceability_state: 'Confirmed', lifecycle: 'established', icp_score: 99, archetype_ml: 'Premium', blinkit_confirmed: true },
  ];
  const plan = buildSequence(locs, { city: 'X', platform: 'all', budget: 18000 }); // one Premium (18000) fits
  assert.equal(plan.waves[1].candidates.length, 2);
  assert.equal(plan.waves[1].affordable.length, 1);
  assert.equal(plan.spent, 18000);
  const p2 = buildSequence(locs, { city: 'X', platform: 'blinkit', budget: 100000 });
  assert.equal(p2.waves[1].candidates.length, 1); // platform filter excludes the non-confirmed one
});
