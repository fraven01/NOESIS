const assert = require('assert');
const { calcNeedsReview } = require('../anlage2_review_utils.js');

const test = require('node:test');

test('manual differs from doc triggers review', () => {
    assert.strictEqual(calcNeedsReview(true, false, true, true), true);
});

test('manual equals doc does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(true, true, false, true), false);
});

test('missing doc triggers review even with manual', () => {
    assert.strictEqual(calcNeedsReview(true, undefined, false, true), true);
});

test('no manual and doc differs from ai triggers review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, false, false), true);
});

test('no manual and doc equals ai does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, true, false), false);
});
