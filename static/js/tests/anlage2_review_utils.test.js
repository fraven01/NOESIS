const assert = require('assert');
const { calcNeedsReview } = require('../anlage2_review_utils.js');

const test = require('node:test');

test('manual differs from doc triggers review', () => {
    assert.strictEqual(calcNeedsReview(true, false, true, true), true);
});

test('manual equals doc does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(true, true, false, true), false);
});

test('manual with undefined doc does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(true, undefined, false, true), false);
});

test('manual with null doc does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(true, null, false, true), false);
});

test('no manual and doc differs from ai triggers review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, false, false), true);
});

test('no manual and doc equals ai does not trigger review', () => {
    assert.strictEqual(calcNeedsReview(undefined, true, true, false), false);
});

test('no manual and null doc triggers review', () => {
    assert.strictEqual(calcNeedsReview(undefined, null, false, false), true);
});
