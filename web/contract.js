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

// Per-locality activation-cost estimates (INR), mirror of contract.py (grounded in GOAT Life's
// disclosed economics — see contract.py). Used by the attack-sequence engine.
export const ACTIVATION_COST = {
  'Premium · Metro': 20000, 'Premium': 18000,
  'Full-infra · Metro': 13000, 'Amenity-rich · Metro': 13000,
  'Employer-dense · Metro': 12000, 'Metro': 11000,
  'Healthcare-rich · Full-infra': 10000, 'Well-connected': 9000,
  'Employer-dense': 9000, 'Average / Mixed': 6000,
};
export const ACTIVATION_COST_DEFAULT = 10000;
export const costFor = (arch) => ACTIVATION_COST[arch] || ACTIVATION_COST_DEFAULT;
