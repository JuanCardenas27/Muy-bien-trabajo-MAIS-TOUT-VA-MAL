import { bogotaDay, formatLong, formatShort } from './dates';

test('formats in Bogota', () => {
  expect(formatShort('2026-10-15T04:30:00.000000Z')).toBe('14 oct 23:30');
  expect(formatLong('2026-10-15T04:30:00.000000Z')).toBe('14 oct 2026 23:30');
  expect(bogotaDay(new Date('2026-10-15T04:30:00Z'))).toBe('2026-10-14');
});
