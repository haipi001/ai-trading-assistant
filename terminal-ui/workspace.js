(() => {
  const groups = {
    'Market monitor': [['WEI','Global indices'],['W','Watchlist'],['MOST','Most active'],['MAP','Sector heatmap'],['FX','FX matrix'],['GOV','Government bonds'],['CMDT','Commodity curves'],['ECO','Economic calendar']],
    'Security analytics': [['AAPL DES','Security overview'],['AAPL GP','Price chart'],['AAPL HP','Historical prices'],['AAPL DEPTH','Market depth'],['AAPL OPT','Option chain'],['AAPL FA','Financial analysis'],['AAPL COMP','Peer comparison']],
    'Research & news': [['TOP','Top stories'],['AAPL N','Security news'],['EQS','Equity screener'],['SRCH','Security search'],['FLDS','Field dictionary']],
    'Integrations & account': [['XL','Office & Spreadsheet'], ['MSG','Messaging & Contacts'], ['FEED','Market Data Setup'], ['BROKER','Broker Connection'], ['ACCOUNT','Account & Entitlements'], ['INBOX','Notification Center'], ['SUPPORT','Help & Diagnostics']],
    'Personal workspace': [['PORT','Portfolio'],['TRD','Trade blotter'],['ORD','Order monitor'],['ALRT','Price alerts'],['SET','Settings & profiles'],['HELP','Command reference'],['WORK','Workspace & accessibility'],['CONN','Data & connections'],['PLUG','Components & integrations'],['ABOUT','About & UI coverage']]
  };
  for (const feature of window.TERMINAL_FEATURES || []) {
    const name = '业务工作区 · ' + feature.page;
    (groups[name] ||= []).push([feature.code, feature.label]);
  }
  const execute = value => {
    const command = document.getElementById('cmd'); command.value = value;
    document.getElementById('gobtn').click();
  };
  const migratedTabs = [['home','AI智搜','研究首页'],['market','图表','专业图表'],['strategy','自动赚币','策略'],['chain','聪明钱','链上'],['assets','总览','资产'],['auth','已授权账户','授权'],['data','加密货币储备','数据']];
  const nav=document.querySelector('.workspace-tabs');
  for(const [page,tab,label] of migratedTabs){const target=(window.TERMINAL_FEATURES||[]).find(item=>item.page===page&&item.tab===tab);if(!target)continue;const button=document.createElement('button');button.className='workspace-tab';button.dataset.command=target.code;button.textContent=label;nav.insertBefore(button,document.getElementById('directory-toggle'));}
  const directory = document.getElementById('function-directory');
  for (const [name, entries] of Object.entries(groups)) {
    const section = document.createElement('section');
    const heading = document.createElement('h2'); heading.textContent = name; section.append(heading);
    for (const [command,label] of entries) {
      const button = document.createElement('button'); button.dataset.command = command;
      const code = document.createElement('b'); code.textContent = command.split(' ').pop();
      const text = document.createElement('span'); text.textContent = label; button.append(code,text); section.append(button);
    }
    directory.append(section);
  }
  const filter = document.createElement('input'); filter.className='directory-search'; filter.type='search'; filter.placeholder='Search functions by name or code…'; filter.setAttribute('aria-label','Search all functions');
  const empty = document.createElement('p'); empty.className='directory-empty'; empty.textContent='No matching functions.'; empty.hidden=true; empty.setAttribute('role','status');
  directory.prepend(filter); directory.append(empty);
  filter.addEventListener('input',()=>{const query=filter.value.trim().toLowerCase();let matches=0;directory.querySelectorAll('section').forEach(section=>{let count=0;section.querySelectorAll('button').forEach(button=>{button.hidden=!button.textContent.toLowerCase().includes(query);if(!button.hidden)count++;});section.hidden=!count;matches+=count;});empty.hidden=matches>0;});
  const toggle = document.getElementById('directory-toggle');
  toggle.addEventListener('click', () => { directory.hidden = !directory.hidden; toggle.setAttribute('aria-expanded', String(!directory.hidden)); if(!directory.hidden)filter.focus(); });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-command]'); if (!button) return;
    execute(button.dataset.command); directory.hidden = true; toggle.setAttribute('aria-expanded','false');
    if (button.dataset.command.startsWith('LAY ')) {
      document.querySelectorAll('.layout-picker button').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    }
  });
  function syncControls() {
    const quad = document.querySelector('.quad');
    const layout = quad ? (quad.classList.contains('quad4') ? '4' : '2') : '1';
    document.querySelectorAll('.layout-picker button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.command === 'LAY ' + layout)));
    const active = document.querySelector('.qcell.focus .qfn') || document.getElementById('phTitle');
    const code = active ? active.textContent.split(' ')[0] : '';
    document.querySelectorAll('.workspace-tab[data-command]').forEach(button => {
      const selected = button.dataset.command.split(' ').pop() === code;
      button.classList.toggle('active',selected); button.setAttribute('aria-current', selected ? 'page' : 'false');
    });
    document.querySelectorAll('.qhd').forEach(header => {
      if (header.querySelector('select')) return;
      const select = document.createElement('select'); select.className = 'panel-function'; select.setAttribute('aria-label','Choose panel function');
      const initial = document.createElement('option'); initial.value = ''; initial.textContent = 'Change function'; select.append(initial);
      for (const [name, entries] of Object.entries(groups)) {
        const group = document.createElement('optgroup'); group.label = name;
        for (const [command,label] of entries) { const option = document.createElement('option'); option.value=command; option.textContent=command.split(' ').pop()+' · '+label; group.append(option); }
        select.append(group);
      }
      select.addEventListener('change', () => { const command=select.value; if (!command) return; header.click(); execute(command); });
      header.append(select);
    });
  }
  const observer = new MutationObserver(syncControls);
  const viewNode=document.getElementById('view');
  if(viewNode)observer.observe(viewNode, {childList:true});
  syncControls();
  document.addEventListener('keydown',event=>{
    if(event.key!=='Tab')return;
    const dialog=Array.from(document.querySelectorAll('[role="dialog"][aria-modal="true"]')).find(el=>!el.classList.contains('hidden'));
    if(!dialog)return;
    const focusable=Array.from(dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex="0"]')).filter(el=>!el.disabled&&el.getClientRects().length);
    if(!focusable.length)return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){event.preventDefault();first.focus();}
  });
  document.addEventListener('click', () => requestAnimationFrame(syncControls));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !directory.hidden) { directory.hidden = true; toggle.setAttribute('aria-expanded','false'); toggle.focus(); } });
})();
