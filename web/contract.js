// Frontend mirror of scripts/contract.py — single source of truth for GTM status colors/labels.
// A pytest (scripts/test_build_locality_data.py) asserts these equal contract.py's GTM_COLORS.
export const GTM_ACTIONS = [
  'PUSH-NOW', 'SAMPLE + QC test', 'SAMPLE (D2C / offline)', 'D2C / OFFLINE - verify QC', 'HOLD',
];

export const GTM_COLORS = {
  'PUSH-NOW':                  '#059669',
  'SAMPLE + QC test':          '#d97706',
  'SAMPLE (D2C / offline)':    '#EF9F27',
  'D2C / OFFLINE - verify QC': '#2a78d6',
  'HOLD':                      '#888780',
};
export const GTM_DEFAULT_COLOR = '#888780';

export const GTM_LABELS = {
  'PUSH-NOW':                  'Push now',
  'SAMPLE + QC test':          'Sample + QC test',
  'SAMPLE (D2C / offline)':    'Sample (D2C / offline)',
  'D2C / OFFLINE - verify QC': 'D2C / offline (verify QC)',
  'HOLD':                      'Hold',
};

export const colorFor = (a) => GTM_COLORS[a] || GTM_DEFAULT_COLOR;
export const labelFor = (a) => GTM_LABELS[a] || a;
