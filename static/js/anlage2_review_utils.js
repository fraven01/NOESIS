function calcNeedsReview(manualVal, docVal, aiVal, hasManual, field) {
    if (field === 'einsatz_bei_telefonica' || field === 'zur_lv_kontrolle') {
        if (hasManual) {
            return docVal !== undefined && manualVal !== docVal;
        }
        return false;
    }
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
