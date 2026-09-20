'use strict';
const screens={'Sign in':login,Register:register,Circles:circles,Marketplace:marketplace,Invitations:invitations,Account:account,Notifications:notifications,Trust:trust,Reports:reports,'Back office':operations};
(async()=>{try{const h=await(await fetch('/health')).json();sandbox=h.sandbox;$('mode').textContent=sandbox?'Sandbox · No real money':'Provider setup required';await navigate(auth?(initialAuthenticatedView()):new URLSearchParams(location.search).get('view')==='register'?'Register':'Sign in');}catch(e){showError(e)}})();

if("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(()=>{});

document.addEventListener('pointerdown',event=>{const host=$('notification-tools'),panel=$('notification-dropdown');if(panel&&!host.contains(event.target)){panel.hidden=true;host.querySelector('button').setAttribute('aria-expanded','false')}});
