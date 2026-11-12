export function researchPrincipal(userId,sessionIdentity){return JSON.stringify([userId||'',sessionIdentity||'']);}
export function researchVisibleMessages(messages,principal){return messages.filter(message=>message.principal===principal);}
