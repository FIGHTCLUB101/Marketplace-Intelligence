import { test } from 'node:test';
import assert from 'node:assert';
import { nextSortState } from '../sortable-table.js';

test('nextSortState: clicking a column with no prior sort starts ascending', () => {
  assert.deepEqual(nextSortState({ key: null, dir: 1 }, 'icp'), { key: 'icp', dir: 1 });
});

test('nextSortState: clicking a different column resets to ascending', () => {
  assert.deepEqual(nextSortState({ key: 'city', dir: -1 }, 'icp'), { key: 'icp', dir: 1 });
});

test('nextSortState: clicking the same column flips direction', () => {
  assert.deepEqual(nextSortState({ key: 'icp', dir: 1 }, 'icp'), { key: 'icp', dir: -1 });
  assert.deepEqual(nextSortState({ key: 'icp', dir: -1 }, 'icp'), { key: 'icp', dir: 1 });
});
