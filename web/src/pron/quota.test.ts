import 'fake-indexeddb/auto';
import { addSeconds, getUsage, monthOf, quotaState, secondsOf } from './quota';

test('quota state boundaries', () =>
  expect([0, 14399, 14400, 17999, 18000].map(quotaState)).toEqual([
    'ok',
    'ok',
    'warn',
    'warn',
    'exceeded',
  ]));

test('month rolls over in Bogota not UTC', () => {
  expect([
    monthOf(new Date('2026-11-01T04:59:59Z')),
    monthOf(new Date('2026-11-01T05:00:00Z')),
  ]).toEqual(['2026-10', '2026-11']);
});

test('seconds round up', () => {
  expect([secondsOf(1840), secondsOf(2000), secondsOf(2001)]).toEqual([
    2, 2, 3,
  ]);
});

test('addSeconds accumulates per month', async () => {
  expect(await getUsage('2026-10')).toBe(0);
  expect(await addSeconds('2026-10', 14000)).toBe(14000);
  expect(await addSeconds('2026-10', 400)).toBe(14400);
  expect(await getUsage('2026-11')).toBe(0);
});
