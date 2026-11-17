(function(){
  var S=document.currentScript, D=S?S.dataset:{};
  var FROM=(D.from||'USD').toUpperCase(), TO=(D.to||'KES').toUpperCase();
  var AMOUNT=parseFloat(D.amount||'100');
  var API=D.api||(new URL(S.src)).origin;
  var THEME=D.theme||'auto';
  var el=document.createElement('div');
  el.setAttribute('role','status');el.setAttribute('aria-live','polite');
  var dark=(THEME==='dark')||(THEME==='auto'&&matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches);
  el.style.cssText='display:inline-flex;gap:8px;align-items:center;padding:8px 12px;'+
    'border-radius:8px;font:500 13px/1.3 ui-monospace,Menlo,monospace;'+
    'background:'+(dark?'#131b2e':'#fff')+';color:'+(dark?'#e6ebf5':'#0b1220')+';'+
    'border:1px solid '+(dark?'#1f2a44':'#e5e9f0')+';';
  el.innerHTML='<span style="opacity:.6">loading…</span>';
  if(S&&S.parentNode) S.parentNode.insertBefore(el,S.nextSibling);
  function fmt(n,d){return new Intl.NumberFormat(undefined,{maximumFractionDigits:d,minimumFractionDigits:d}).format(n);}
  function load(){
    fetch(API+'/convert',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({from:FROM,to:TO,amount:AMOUNT,side:'mid'})})
      .then(function(r){return r.json();})
      .then(function(r){
        if(r.detail){el.innerHTML='<span style="color:#dc2626">'+r.detail+'</span>';return;}
        var dot='<span style="width:6px;height:6px;border-radius:50%;background:#16a34a;display:inline-block"></span>';
        el.innerHTML=dot+' '+fmt(AMOUNT,2)+' '+FROM+' = <b>'+fmt(r.to.amount,2)+' '+TO+'</b>'+
          ' <span style="opacity:.6">· '+fmt(r.confidence*100,0)+'% conf</span>';
      })
      .catch(function(){el.innerHTML='<span style="color:#dc2626">unavailable</span>';});
  }
  load(); setInterval(load,30000);
})();
