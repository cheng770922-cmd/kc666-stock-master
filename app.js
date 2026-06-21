const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const fmt=n=>Number(n||0).toLocaleString('zh-TW',{maximumFractionDigits:2});
const signed=n=>`${n>0?'+':''}${fmt(n)}`;
const cls=n=>n>0?'positive':n<0?'negative':'';
let DATA=null, rankType='strong', etfIndex=0, detailData=null;

async function api(url){const r=await fetch(url);const d=await r.json();if(!r.ok||d.error)throw new Error(d.error||'資料讀取失敗');return d}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),1800)}
function stockCell(s){return `<div class="stock-link" data-code="${s.code}"><span class="avatar">${s.name.slice(0,1)}</span><div><strong>${s.name}</strong><small>${s.code}</small></div></div>`}

function renderMarket(){
  const {index,breadth}=DATA,total=breadth.total||1;
  $('#headerDate').textContent=DATA.asOf;
  $('#dataNote').textContent=`${DATA.asOfLabel}・6/19 端午節休市，採最近交易日資料`;
  $('#taiex').textContent=fmt(index.close);
  $('#taiexChange').className=cls(index.change);$('#taiexChange').textContent=`${signed(index.change)}　${signed(index.pct)}%`;
  $('#upCount').textContent=fmt(breadth.up);$('#downCount').textContent=fmt(breadth.down);$('#flatCount').textContent=fmt(breadth.flat);
  $('#upPct').textContent=`${(breadth.up/total*100).toFixed(1)}%`;$('#downPct').textContent=`${(breadth.down/total*100).toFixed(1)}%`;$('#totalCount').textContent=`共 ${fmt(total)} 檔`;
  $('#sources').textContent=`資料來源：${DATA.sources.join('・')}｜更新 ${DATA.asOf}`;
}
function rangePos(s){const range=s.high-s.low;return range?Math.max(0,Math.min(100,(s.close-s.low)/range*100)):50}
function renderRank(){
  const rows=DATA[rankType];
  $('#rankBody').innerHTML=rows.map((s,i)=>`<tr><td class="rank-no">${String(i+1).padStart(2,'0')}</td><td>${stockCell(s)}</td><td><span class="market-tag">${s.market}</span></td><td>${fmt(s.close)}</td><td class="${cls(s.change)}">${signed(s.change)}</td><td class="${cls(s.pct)}"><strong>${signed(s.pct)}%</strong></td><td>${fmt(s.volume)} 張</td><td><div class="range-bar" title="低 ${fmt(s.low)}・高 ${fmt(s.high)}"><i style="left:calc(${rangePos(s)}% - 4px)"></i></div></td><td><button class="research-btn" data-code="${s.code}">研究</button></td></tr>`).join('');
  $('#rankFooter').textContent=`完整列出 ${rows.length} 名・${rankType==='strong'?'漲幅由高至低':'跌幅由深至淺'}`; bindStocks();
}
function renderEtf(){
  $('#etfSelector').innerHTML=DATA.etfs.map((e,i)=>`<button class="${i===etfIndex?'active':''}" data-etf="${i}"><strong>${e.code}</strong><span>${e.name}</span></button>`).join('');
  const e=DATA.etfs[etfIndex],c=e.counts;
  $('#etfSummary').innerHTML=`${['新增','加碼','減碼','剔除'].map(k=>`<span class="summary-pill">${k}<strong>${c[k]||0} 檔</strong></span>`).join('')}<span class="summary-pill asof">持股基準 ${e.asOf}</span>`;
  const kindClass={'新增':'add','剔除':'remove','加碼':'boost','減碼':'reduce'};
  $('#etfBody').innerHTML=e.changes.length?e.changes.map(x=>`<tr><td><span class="change-badge ${kindClass[x.kind]}">${x.kind}</span></td><td>${stockCell(x)}</td><td>${fmt(x.shares)} 股</td><td class="${cls(x.delta)}">${signed(x.delta)} 股</td><td>${x.weight?x.weight.toFixed(2)+'%':'—'}</td></tr>`).join(''):`<tr><td colspan="5">最近兩次揭露持股無異動</td></tr>`;
  $$('#etfSelector button').forEach(b=>b.onclick=()=>{etfIndex=+b.dataset.etf;renderEtf()});bindStocks();
}
function renderInstitutions(){
  const list=DATA.institutions;$('#instCount').textContent=`共 ${list.length} 檔`;
  $('#instBody').innerHTML=list.length?list.map((s,i)=>`<tr><td class="rank-no">${String(i+1).padStart(2,'0')}</td><td>${stockCell(s)}</td><td>${fmt(s.close)}</td><td class="${cls(s.pct)}">${signed(s.pct)}%</td><td class="positive">+${fmt(s.foreign)}</td><td class="positive">+${fmt(s.trust)}</td><td class="positive">+${fmt(s.dealer)}</td><td class="positive"><strong>+${fmt(s.total)}</strong></td><td><button class="research-btn" data-code="${s.code}">研究</button></td></tr>`).join(''):`<tr><td colspan="9">最近交易日無符合三大法人同步買超條件的普通股</td></tr>`;bindStocks();
}
function bindStocks(){$$('[data-code]').forEach(el=>el.onclick=e=>{e.stopPropagation();openStock(el.dataset.code)})}

$('#rankTabs').onclick=e=>{const b=e.target.closest('button');if(!b)return;rankType=b.dataset.list;$$('#rankTabs button').forEach(x=>x.classList.toggle('active',x===b));renderRank()};

let searchTimer;
$('#searchInput').oninput=()=>{clearTimeout(searchTimer);const q=$('#searchInput').value.trim();if(!q){$('#searchPopover').classList.remove('show');return}searchTimer=setTimeout(async()=>{try{const rows=await api(`/api/search?q=${encodeURIComponent(q)}`);$('#searchPopover').innerHTML=rows.length?rows.map(s=>`<div class="search-row" data-code="${s.code}"><span class="avatar">${s.name.slice(0,1)}</span><div><strong>${s.name}</strong><small>${s.code}・${s.market}</small></div><em class="${cls(s.pct)}">${signed(s.pct)}%</em></div>`).join(''):'<div class="search-row"><small>找不到符合的上市櫃普通股</small></div>';$('#searchPopover').classList.add('show');bindStocks()}catch(e){toast(e.message)}},250)};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#searchInput').focus()}if(e.key==='Escape')closeStock()});
document.addEventListener('click',e=>{if(!e.target.closest('.search-box'))$('#searchPopover').classList.remove('show')});

async function openStock(code){
  $('#searchPopover').classList.remove('show');$('#researchDrawer').classList.add('open');$('#backdrop').classList.add('show');$('#researchDrawer').setAttribute('aria-hidden','false');$('#researchLoading').classList.remove('hide');$('#researchContent').innerHTML='';
  try{detailData=await api(`/api/stock?code=${encodeURIComponent(code)}`);renderResearch()}catch(e){$('#researchLoading').classList.add('hide');$('#researchContent').innerHTML=`<div class="error-box"><h3>個股資料暫時無法讀取</h3><p>${e.message}</p><button class="research-btn" onclick="closeStock()">關閉</button></div>`}
}
function closeStock(){$('#researchDrawer').classList.remove('open');$('#backdrop').classList.remove('show');$('#researchDrawer').setAttribute('aria-hidden','true')}
$('#backdrop').onclick=closeStock;

function renderResearch(){
  const s=detailData.stock;
  $('#researchContent').innerHTML=`<div class="research-head"><div class="drawer-top"><span class="avatar">${s.name.slice(0,1)}</span><div><h2>${s.name}</h2><p>${s.code}・${s.market}普通股</p></div><button class="close-btn" aria-label="關閉個股研究">×</button></div><div class="quote-row"><strong>${fmt(s.close)}</strong><span class="${cls(s.pct)}">${signed(s.change)}　${signed(s.pct)}%</span><small>${detailData.asOf} 收盤</small></div></div><div class="research-tabs"><button class="active" data-view="chart">K 棒技術線</button><button data-view="chips">籌碼面</button><button data-view="news">相關新聞</button></div><div class="research-view" id="researchView"></div>`;
  $('.close-btn').onclick=closeStock;$$('.research-tabs button').forEach(b=>b.onclick=()=>{$$('.research-tabs button').forEach(x=>x.classList.toggle('active',x===b));renderResearchView(b.dataset.view)});renderResearchView('chart');$('#researchLoading').classList.add('hide');
}
function renderResearchView(view){
  const s=detailData.stock;
  if(view==='chart'){
    $('#researchView').innerHTML=`<div class="chart-toolbar"><strong>日 K・近 60 個交易日</strong><div class="legend"><span><i class="r"></i>上漲</span><span><i class="g"></i>下跌</span><span><i class="m"></i>MA 10</span></div></div><div class="candle-chart" id="candleChart"></div><div class="detail-cards"><div class="detail-card"><small>開盤</small><strong>${fmt(s.open)}</strong></div><div class="detail-card"><small>最高</small><strong>${fmt(s.high)}</strong></div><div class="detail-card"><small>最低</small><strong>${fmt(s.low)}</strong></div><div class="detail-card"><small>收盤</small><strong>${fmt(s.close)}</strong></div><div class="detail-card"><small>成交量</small><strong>${fmt(s.volume)} 張</strong></div></div>`;drawCandles(detailData.candles.slice(-60));
  }else if(view==='chips'){
    const c=detailData.chips;$('#researchView').innerHTML=`<div class="chip-grid">${[['外資',c.foreign],['投信',c.trust],['自營商',c.dealer]].map(x=>`<article class="chip-card"><header><span>${x[0]}</span><span>${detailData.asOf}</span></header><strong class="${cls(x[1])}">${signed(x[1])} 張</strong><p>${x[1]>0?'當日淨買超':x[1]<0?'當日淨賣超':'當日買賣超為零'}</p></article>`).join('')}</div><div class="chip-note">籌碼資料直接採用證交所／櫃買中心三大法人日報。外資、投信與自營商分開呈現，避免將法人數據誤標成「主力」。</div>`;
  }else{
    $('#researchView').innerHTML=detailData.news.length?`<div class="news-grid">${detailData.news.map(n=>`<a class="news-card" href="${n.link}" target="_blank" rel="noopener"><p>${n.title}</p><span>${n.source}・${formatNewsDate(n.date)}</span></a>`).join('')}</div>`:'<div class="error-box">最近 14 天找不到相關新聞</div>';
  }
}
function formatNewsDate(x){const d=new Date(x);return isNaN(d)?x:new Intl.DateTimeFormat('zh-TW',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)}
function drawCandles(c){
  if(!c.length){$('#candleChart').textContent='無可用 K 線資料';return}
  const W=820,H=360,p={l:12,r:56,t:12,b:26},priceH=260,volTop=292,volH=45;
  const lo=Math.min(...c.map(x=>x.low)),hi=Math.max(...c.map(x=>x.high)),maxV=Math.max(...c.map(x=>x.volume));
  const x=i=>p.l+(W-p.l-p.r)*(i+.5)/c.length,y=v=>p.t+(hi-v)/(hi-lo||1)*priceH,bw=Math.max(2,(W-p.l-p.r)/c.length*.58);
  let svg=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  for(let i=0;i<5;i++){const yy=p.t+priceH*i/4,val=hi-(hi-lo)*i/4;svg+=`<line class="chart-grid" x1="${p.l}" y1="${yy}" x2="${W-p.r}" y2="${yy}"/><text class="chart-label" x="${W-p.r+7}" y="${yy+3}">${fmt(val)}</text>`}
  const ma=[];c.forEach((d,i)=>{const up=d.close>=d.open,xx=x(i),yo=y(d.open),yc=y(d.close),yh=y(d.high),yl=y(d.low),top=Math.min(yo,yc),height=Math.max(1,Math.abs(yc-yo));svg+=`<line class="${up?'wick-up':'wick-down'}" x1="${xx}" y1="${yh}" x2="${xx}" y2="${yl}"/><rect class="${up?'body-up':'body-down'}" x="${xx-bw/2}" y="${top}" width="${bw}" height="${height}"><title>${d.date} 開 ${fmt(d.open)} 高 ${fmt(d.high)} 低 ${fmt(d.low)} 收 ${fmt(d.close)}</title></rect><rect class="${up?'body-up':'body-down'}" opacity=".45" x="${xx-bw/2}" y="${volTop+volH-d.volume/maxV*volH}" width="${bw}" height="${d.volume/maxV*volH}"/>`;if(i>=9)ma.push(`${xx},${y(c.slice(i-9,i+1).reduce((a,z)=>a+z.close,0)/10)}`)});svg+=`<polyline class="ma-line" points="${ma.join(' ')}"/>`;
  [0,Math.floor(c.length/2),c.length-1].forEach(i=>svg+=`<text class="chart-label" x="${x(i)-18}" y="${H-5}">${c[i].date.slice(5)}</text>`);svg+='</svg>';$('#candleChart').innerHTML=svg;
}

async function init(){try{DATA=await api('/api/market');renderMarket();renderRank();renderEtf();renderInstitutions();$('#loading').classList.add('hide')}catch(e){$('#loading').innerHTML=`<div class="loader-mark">!</div><strong>資料載入失敗</strong><span>${e.message}</span><button class="research-btn" onclick="location.reload()">重新載入</button>`}}
init();
