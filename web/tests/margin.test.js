import { test } from 'node:test';
import assert from 'node:assert';
import { calcEconomics, getVerdict } from '../margin.js';

test('netRealization = effSP*(1-commission) - fulfilment', () => {
  const r = calcEconomics({ mrp:119, grossMarginPercent:57, brandDiscountPercent:16,
    commissionRate:0.179, fulfilmentFee:50, logisticsRate:0.10, returnsRate:0.025,
    monthlyAdBudget:250000, monthlyOrders:500 });
  assert.ok(Math.abs(r.netRealization - 32.07) < 0.5);
});

test('verdict STOP when margin below 50', () => {
  assert.equal(getVerdict({grossMarginPercent:45, netRealization:300, monthlyAdBudget:300000}), 'STOP');
});
test('verdict GO when all thresholds clear', () => {
  assert.equal(getVerdict({grossMarginPercent:70, netRealization:260, monthlyAdBudget:250000}), 'GO');
});
test('verdict CAUTION in the middle', () => {
  assert.equal(getVerdict({grossMarginPercent:60, netRealization:200, monthlyAdBudget:150000}), 'CAUTION');
});
