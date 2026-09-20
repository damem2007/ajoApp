'use strict';
const $=id=>document.getElementById(id), root=$('workspace');
let formCounter=0;
let auth=JSON.parse(sessionStorage.getItem('ajoSession')||'null'), me=null, sandbox=false, page='Circles';
const E=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==null&&text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e};
const money=(n,c)=>new Intl.NumberFormat(undefined,{style:'currency',currency:c}).format(n/100);
let toastTimer;
function message(text,error=false){clearTimeout(toastTimer);const box=$('message');box.replaceChildren();box.hidden=!text;if(!text)return;box.className='toast '+(error?'error':'success');box.setAttribute('role',error?'alert':'status');box.setAttribute('aria-live',error?'assertive':'polite');box.append(E('strong',error?'Please check this':'Update'),E('p',text));const close=E('button','Dismiss','secondary');close.type='button';close.onclick=()=>message('');box.append(close);if(!error)toastTimer=setTimeout(()=>message(''),6000);}
function showError(error){message(error instanceof TypeError?'We couldn’t connect. Check your connection and try again.':error.message||'Something went wrong. Please try again.',true)}

function saveAuth(value){auth=value;value?sessionStorage.setItem('ajoSession',JSON.stringify(value)):sessionStorage.removeItem('ajoSession');}
async function api(path,body,method,raw=false){
 const options={method:method||(body?'POST':'GET'),headers:{}};if(auth)options.headers.Authorization='Bearer '+auth.access_token;
 if(body instanceof FormData)options.body=body;else if(body!==undefined&&body!==null){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
 let r=await fetch('/api/v1'+path,options);
 if(r.status===401&&auth&&path!='/auth/refresh'){
  const ref=await fetch('/api/v1/auth/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:auth.refresh_token})});
  if(ref.ok){saveAuth(await ref.json());options.headers.Authorization='Bearer '+auth.access_token;r=await fetch('/api/v1'+path,options);}
 }
 if(!r.ok){let err;try{err=await r.json()}catch{err={detail:'Request failed'}}const detail=Array.isArray(err.errors)&&err.errors.length?[...new Set(err.errors.map(item=>item.message))].join(' '):typeof err.detail==='string'?err.detail:'Please check your entries and try again.';const friendly={'Invalid credentials':'That email or password doesn’t match. Please try again.','Invalid MFA code':'That authenticator code doesn’t match. Enter the current six-digit code from your app.','Circle is full':'This circle has reached its member limit. Please choose another circle.','Concurrent scheme cap reached':'You’ve reached your current circle limit. Complete an existing commitment before joining another circle.'};const e=Error(friendly[detail]||detail);e.fields=Array.isArray(err.errors)?err.errors:[];throw e;}
 return raw?r.blob():r.status===204?null:r.json();
}
function button(parent,label,action,cls){const b=E('button',label,cls);b.type='button';b.onclick=async()=>{b.disabled=true;message('');try{await action()}catch(e){showError(e)}finally{b.disabled=false}};parent.append(b);return b;}
function title(text,sub){root.append(E('h1',text));if(sub)root.append(E('p',sub));}
function card(parent,title){const c=E('article',null,'card');if(title)c.append(E('h2',title));parent.append(c);return c;}
function data(parent,value){const pre=E('pre',JSON.stringify(value,null,2));parent.append(pre);return pre;}
function table(parent,heads,rows){const wrap=E('div',null,'scroll'),t=E('table'),thead=E('thead'),tr=E('tr');heads.forEach(h=>tr.append(E('th',h)));thead.append(tr);t.append(thead);const body=E('tbody');rows.forEach(row=>{const tr=E('tr');row.forEach(x=>{const td=E('td');td.append(x instanceof Node?x:document.createTextNode(String(x??'—')));tr.append(td)});body.append(tr)});t.append(body);wrap.append(t);parent.append(wrap);}
function form(parent,fields,label,submit){const prefix='form-'+(++formCounter)+'-';const f=E('form',null,'panel'),grid=E('div',null,'fields'),controls={};f.noValidate=true;f.append(grid);
 fields.forEach(def=>{const [key,name,type='text',value='',options]=def,wrap=E('div'),lab=E('label',name);lab.htmlFor=prefix+key;let input;
  if(type==='select'){input=E('select');options.forEach(v=>{const o=E('option',Array.isArray(v)?v[1]:v);o.value=Array.isArray(v)?v[0]:v;input.append(o)})}else input=E(type==='textarea'?'textarea':'input');
  if(type!=='select'&&type!=='textarea')input.type=type;input.id=prefix+key;input.name=key;
  if(type==='checkbox')input.checked=!!value;else if(type!=='file')input.value=value;
  input.required=!['checkbox','file'].includes(type)&&!name.includes('(optional)');if(type==='number')input.step='1';
  if(type==='password')input.autocomplete=key==='password'?'current-password':'off';wrap.append(lab,input);if(page==='Register'&&key==='phone'){const hint=E('p','Include + and country code, for example +14165551234.','muted');wrap.append(hint);input.autocomplete='tel'}if(page==='Register'&&key==='password'){input.autocomplete='new-password';wrap.append(E('p','Use at least 12 characters.','muted'))}grid.append(wrap);controls[key]=input;
 });const b=E('button',label);b.type='submit';f.append(b);f.onsubmit=async ev=>{ev.preventDefault();b.disabled=true;message('');try{const errors=[];for(const [key,name] of fields){const input=controls[key];input.removeAttribute('aria-invalid');const old=document.getElementById(input.id+'-error');if(old)old.textContent='';if(!input.checkValidity()){errors.push({field:key,message:input.validity.valueMissing?'Please enter '+name.toLowerCase()+'.':input.type==='email'?'Enter a valid email address.':'Check '+name.toLowerCase()+' and try again.'})}if(page==='Register'&&key==='password'&&input.value&&input.value.length<12)errors.push({field:key,message:'Use a password with at least 12 characters.'})}if(errors.length){const error=Error([...new Set(errors.map(item=>item.message))].join(' '));error.fields=errors;throw error}const values={};fields.forEach(([key,,type])=>values[key]=type==='checkbox'?controls[key].checked:type==='number'?Number(controls[key].value):type==='file'?controls[key].files[0]:controls[key].value);await submit(values,controls)}catch(e){for(const item of e.fields||[]){const input=controls[item.field];if(!input)continue;input.setAttribute('aria-invalid','true');let hint=document.getElementById(input.id+'-error');if(!hint){hint=E('p',null,'field-error');hint.id=input.id+'-error';input.after(hint);input.setAttribute('aria-describedby',hint.id)}hint.textContent=item.message;input.oninput=()=>{input.removeAttribute('aria-invalid');hint.textContent=''}}const first=Object.values(controls).find(i=>i.getAttribute('aria-invalid')==='true');if(first)first.focus();showError(e)}finally{b.disabled=false}};parent.append(f);return f;
}
async function download(path,name){const blob=await api(path,null,'GET',true),link=E('a');link.href=URL.createObjectURL(blob);link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}
async function navigate(next){page=next;root.replaceChildren();message('');try{if(auth){me=await api('/me');$('profile').textContent=(me.pseudonym||me.email)+' · '+me.role;}renderNav();await refreshBell();await screens[next]();}catch(e){showError(e)}}
function renderNav(){const nav=$('navigation');nav.replaceChildren();if(!auth)return;['Circles','Marketplace','Invitations','Account','Notifications','Trust','Reports',...(me&&me.role!=='member'?['Back office']:[])].forEach(n=>button(nav,n,()=>navigate(n),page===n?'active':''));button(nav,'Sign out',async()=>{await api('/auth/logout',{});saveAuth(null);me=null;$('profile').textContent='';await navigate('Sign in')},'secondary');}
