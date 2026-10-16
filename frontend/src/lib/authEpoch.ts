// Discard authentication failures from requests sent before an account change.
let epoch = 0
export function authRequestEpoch() { return epoch }
export function invalidateAuthRequests() { epoch += 1 }
