// Workspace identity is independent of market data origin and execution permission.
const text = value => typeof value === 'string' && value.trim() ? value.trim().slice(0,128) : null;
export function workspaceIdentity(input = {}) {
  return JSON.stringify([text(input.page),text(input.tab),text(input.asset_class),text(input.symbol),text(input.venue),text(input.timeframe),text(input.user_id),text(input.source),text(input.account_id),['DEMO','PAPER','LIVE'].includes(input.mode)?input.mode:null,text(input.chain_id),text(input.contract_address),text(input.wallet_id)]);
}
export function nextWorkspaceContext(previous, input, now = Date.now()) {
  const identity = workspaceIdentity(input);
  return Object.freeze({workspace_id:'terminal-main',identity,
    context_version:previous ? previous.context_version + (previous.identity !== identity ? 1 : 0) : 1,
    user_id:text(input.user_id),page:text(input.page),tab:text(input.tab),asset_class:text(input.asset_class),symbol:text(input.symbol),
    venue:text(input.venue),timeframe:text(input.timeframe),account_id:text(input.account_id),
    chain_id:text(input.chain_id),contract_address:text(input.contract_address),wallet_id:text(input.wallet_id),
    mode:['DEMO','PAPER','LIVE'].includes(input.mode)?input.mode:null,
    source:text(input.source),updated_at:new Date(now).toISOString()});
}
export function workspaceHistory(messages, context) {
  return messages.filter(message => message.workspaceIdentity === context.identity);
}
