import {backend} from './backend-service.mjs';
import {createIdentityCatalog} from './identity-catalog.mjs';
export const identities=createIdentityCatalog({request:backend.request,identity:backend.identity,notify:()=>window.dispatchEvent(new Event('terminal:identity-options'))});
window.addEventListener('terminal:session-changed',()=>identities.invalidate());
