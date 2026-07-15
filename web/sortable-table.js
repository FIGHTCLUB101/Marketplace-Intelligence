// Shared click-to-sort behavior for Leaderboard's table and all 4 Gems tables —
// one implementation instead of five, since the interaction is identical everywhere.

// Pure: given the current sort state and the key of the column just clicked,
// returns the next sort state. Clicking a new column always starts ascending;
// clicking the already-active column flips direction.
export function nextSortState(current, clickedKey) {
  if (current.key === clickedKey) {
    return { key: clickedKey, dir: -current.dir };
  }
  return { key: clickedKey, dir: 1 };
}

// DOM-coupled: wires click handlers onto every th[data-sort-key] inside tableEl,
// sorts `rows` by the active column's comparator, and writes renderRow(row) output
// into tableEl's <tbody>. Not unit-tested (no DOM harness in this repo) — verified
// manually per the plan's regression-pass task.
export function wireSortableTable(tableEl, rows, columns, renderRow) {
  let state = { key: null, dir: 1 };

  const render = () => {
    const col = columns.find((c) => c.key === state.key);
    const sorted = col ? [...rows].sort((a, b) => state.dir * col.sort(a, b)) : rows;
    tableEl.querySelector('tbody').innerHTML = sorted.map(renderRow).join('');
  };

  tableEl.querySelectorAll('th[data-sort-key]').forEach((th) => {
    th.addEventListener('click', () => {
      state = nextSortState(state, th.dataset.sortKey);
      tableEl.querySelectorAll('th[data-sort-key]').forEach((h) => h.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(state.dir === 1 ? 'sorted-asc' : 'sorted-desc');
      render();
    });
  });

  render();
}
