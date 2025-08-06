function calcNeedsReview(manualVal, docVal, aiVal, hasManual) {
    const docMissing = docVal === undefined || docVal === null;
    const aiMissing = aiVal === undefined || aiVal === null;
    if (hasManual) {
        if (docMissing) {
            return false;
        }
        return manualVal !== docVal;
    }
    if (docMissing) {
        return true;
    }
    if (aiMissing) {
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
