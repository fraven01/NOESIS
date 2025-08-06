const assert = require('assert');
const { calcNeedsReview } = require('../anlage2_review_utils.js');

const test = require('node:test');

test('manual differs from doc triggers review', () => {
    assert.strictEqual(calcNeedsReview(true, false, true, true, 'technisch_vorhanden'), true);
});

test('manual equals doc does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(true, true, false, true, 'technisch_vorhanden'), false);
});

test('missing doc triggers review even with manual', () => {
    assert.strictEqual(calcNeedsReview(true, undefined, false, true, 'technisch_vorhanden'), true);
});

test('no manual and doc differs from ai triggers review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, false, false, 'technisch_vorhanden'), true);
});

test('no manual and doc equals ai does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, true, false, 'technisch_vorhanden'), false);
});

test('no review when parser missing for special field', () => {
    assert.strictEqual(calcNeedsReview(true, undefined, false, true, 'einsatz_bei_telefonica'), false);
});

test('special field manual differs from parser triggers review', () => {
    assert.strictEqual(calcNeedsReview(true, false, undefined, true, 'einsatz_bei_telefonica'), true);
});

test('special field without manual never needs review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, false, false, 'einsatz_bei_telefonica'), false);
});
