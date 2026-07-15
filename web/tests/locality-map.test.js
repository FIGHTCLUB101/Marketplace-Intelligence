import { test } from 'node:test';
import assert from 'node:assert';
import { circlePolygon } from '../locality-map.js';

test('circlePolygon: returns a closed Polygon feature with the given color', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669');
  assert.strictEqual(f.type, 'Feature');
  assert.strictEqual(f.geometry.type, 'Polygon');
  assert.strictEqual(f.properties.color, '#059669');
});

test('circlePolygon: ring has points+1 coordinates and is closed', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669', 32);
  const ring = f.geometry.coordinates[0];
  assert.strictEqual(ring.length, 33);
  assert.deepStrictEqual(ring[0], ring[ring.length - 1]);
});

test('circlePolygon: respects a custom points count', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669', 8);
  assert.strictEqual(f.geometry.coordinates[0].length, 9);
});
