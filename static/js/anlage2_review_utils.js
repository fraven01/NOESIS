function calcNeedsReview(manualVal, docVal, aiVal, hasManual) {
    if (hasManual) {
        return docVal === undefined || manualVal !== docVal;
    }
    if (docVal === undefined) {
        return true;
    }
    if (aiVal === undefined) {
        return false;
    }
    return docVal !== aiVal;
}

if (typeof window !== 'undefined') {
    window.calcNeedsReview = calcNeedsReview;
}
if (typeof module !== 'undefined') {
    module.exports = { calcNeedsReview };
}
