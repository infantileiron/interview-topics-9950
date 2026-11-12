export const resourceEvents=new EventTarget();
export function refreshResources(){resourceEvents.dispatchEvent(new Event('refresh'))}
